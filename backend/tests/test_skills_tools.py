"""Skills de especialistas (versionadas), tools por agente con texto editable, dudas frecuentes y tiempos del agente."""
from sqlalchemy import select

from app.ia import agente as motor
from app.ia import supervisores
from app.models import AgenteIA, ClienteCampana, Deuda, Llamada


def _cuerpo_agente(a: dict, **cambios) -> dict:
    campos = ["nombre", "voz_deepgram", "velocidad_voz", "tono", "personalidad", "severidad", "id_guion", "id_politica",
              "activo", "espera_inicio_seg", "silencio_fin_seg", "silencio_max_seg"]
    d = {k: a[k] for k in campos}
    d["velocidad_voz"] = float(d["velocidad_voz"])
    for k in ("espera_inicio_seg", "silencio_fin_seg", "silencio_max_seg"):
        d[k] = float(d[k])
    d["skills"] = [s["id_skill"] for s in a["skills"]]
    d.update(cambios)
    return d


def test_skills_versionadas_y_asignadas_al_agente(admin, db):
    nueva = {"nombre": "Empatía ante desempleo", "ambito": "AGENTE", "cuando_usar": "El cliente dice que perdió el empleo",
             "contenido": "Reconoce la situación sin juzgar y propone un abono pequeño con fecha cercana y concreta.",
             "autor": "Lic. Especialista en cobranza"}
    sk = admin.post("/api/skills", json=nueva).json()
    assert sk["version"] == 1 and sk["estado"] == "BORRADOR"
    ag = admin.get("/api/agentes").json()[0]
    assert admin.put(f"/api/agentes/{ag['id_agente']}", json=_cuerpo_agente(ag, skills=[sk["id_skill"]])).status_code == 422
    admin.post(f"/api/skills/{sk['id_skill']}/publicar")
    r = admin.put(f"/api/agentes/{ag['id_agente']}", json=_cuerpo_agente(ag, skills=[sk["id_skill"]],
                                                                       espera_inicio_seg=0, silencio_fin_seg=2,
                                                                       silencio_max_seg=8))
    assert r.status_code == 200, r.text
    assert [s["nombre"] for s in r.json()["skills"]] == ["Empatía ante desempleo"]
    assert r.json()["silencio_fin_seg"] == "2.0" and r.json()["silencio_max_seg"] == "8.0"
    v2 = admin.post("/api/skills", json={**nueva, "contenido": nueva["contenido"] + " Versión revisada."}).json()
    assert v2["version"] == 2 and v2["estado"] == "BORRADOR"  # la v1 no se edita: se crea otra
    assert admin.post(f"/api/skills/{sk['id_skill']}/archivar").status_code == 409  # asignada a un agente activo
    db.expire_all()
    a = db.get(AgenteIA, ag["id_agente"])
    d = db.execute(select(Deuda).where(Deuda.estado == "ACTIVA")).scalars().first()
    ll = motor.iniciar(db, agente=a, cliente=d.cliente, deuda=d, canal="TEXTO", modo="PRUEBA")
    system = motor.construir_system(db, ll)
    assert "negociador senior" in system and "ACUERDO DE PAGO REAL" in system and "Empatía ante desempleo" in system
    db.rollback()
    admin.put(f"/api/agentes/{ag['id_agente']}", json=_cuerpo_agente(ag, skills=[]))


def test_skills_del_supervisor(admin, db):
    sk = admin.post("/api/skills", json={
        "nombre": "Criterio de acuerdo concreto", "ambito": "SUPERVISOR", "cuando_usar": "Al evaluar el cierre",
        "contenido": "Un acuerdo válido tiene monto y fecha explícitos confirmados por el cliente en la llamada.",
        "autor": "Supervisora de calidad"}).json()
    assert "Criterio de acuerdo concreto" not in supervisores.skills_supervisor(db)  # aún en borrador
    admin.post(f"/api/skills/{sk['id_skill']}/publicar")
    db.expire_all()
    assert "Criterio de acuerdo concreto" in supervisores.skills_supervisor(db)


def test_tools_por_agente_y_texto_editable(admin, db):
    catalogo = {h["nombre"]: h for h in admin.get("/api/herramientas").json()}
    assert catalogo["verificar_identidad"]["basica"] and not catalogo["dar_aviso_legal"]["basica"]
    assert admin.post("/api/herramientas/dar_aviso_legal/versiones",
                      json={"descripcion": "Lee el aviso legal al inicio de la llamada, después de saludar."}).status_code == 422
    r = admin.post("/api/herramientas/dar_aviso_legal/versiones", json={
        "descripcion": "Lee el aviso legal al inicio de la llamada, después de saludar.",
        "texto_respuesta": "Esta llamada se graba por calidad. Le habla {empresa}."})
    assert r.status_code == 201 and r.json()["version"] >= 1
    ag = admin.get("/api/agentes").json()[0]
    r = admin.put(f"/api/agentes/{ag['id_agente']}", json=_cuerpo_agente(ag, herramientas=["dar_aviso_legal"]))
    assert r.status_code == 200, r.text
    assert set(r.json()["herramientas"]) == set(motor.HERRAMIENTAS_BASICAS) | {"dar_aviso_legal"}
    assert admin.put(f"/api/agentes/{ag['id_agente']}", json=_cuerpo_agente(ag, herramientas=["borrar_todo"])).status_code == 422
    db.expire_all()
    a = db.get(AgenteIA, ag["id_agente"])
    d = db.execute(select(Deuda).where(Deuda.estado == "ACTIVA")).scalars().first()
    ll = motor.iniciar(db, agente=a, cliente=d.cliente, deuda=d, canal="TEXTO", modo="PRUEBA")
    ej = motor.EjecutorHerramientas(db, ll, "ya pagué")
    assert ej.ejecutar("reportar_pago_realizado", {}) == {"error": "Herramienta no autorizada"}  # desactivada
    aviso = ej.ejecutar("dar_aviso_legal", {})["aviso"]
    assert aviso.startswith("Esta llamada se graba") and "{empresa}" not in aviso
    assert [t["name"] for t in motor.herramientas_agente(db, a)][-1] == "dar_aviso_legal"
    db.rollback()
    admin.put(f"/api/agentes/{ag['id_agente']}", json=_cuerpo_agente(ag, herramientas=None))


def test_dudas_frecuentes_y_pago_reportado(admin, db):
    assert admin.post("/api/preguntas-frecuentes", json={
        "pregunta": "¿Dónde puedo pagar?", "palabras_clave": "pagar banco agencia deposito cuenta",
        "respuesta": "Puede pagar en cualquier agencia del banco o por transferencia a la cuenta de la empresa."}).status_code == 201
    a = db.execute(select(AgenteIA).where(AgenteIA.activo.is_(True), AgenteIA.id_guion.is_not(None))).scalars().first()
    cc = db.execute(select(ClienteCampana).where(ClienteCampana.estado_gestion == "PENDIENTE")).scalars().first()
    ll = motor.iniciar(db, agente=a, cliente=cc.cliente, deuda=cc.deuda, canal="TEXTO", modo="PRUEBA", cc=cc)
    ej = motor.EjecutorHerramientas(db, ll, "")
    r = ej.ejecutar("consultar_dudas", {"pregunta": "¿en qué banco puedo pagar?"})
    assert r["encontrada"] and "agencia" in r["respuesta"]
    assert ej.ejecutar("consultar_opciones_pago", {}) == {"error": "Identidad no verificada."}
    assert ej.ejecutar("reportar_pago_realizado", {"detalle": "deposité el lunes"})["registrado"]
    db.flush()
    assert db.get(ClienteCampana, cc.id).estado_gestion == "PAGO_REPORTADO"  # bloqueo: ya no se le marca
    db.rollback()


def test_agente_local_lee_el_aviso_legal(admin, db):
    """Con la tool activa, el agente lee el aviso apenas el titular confirma quién es."""
    from app.ia import proveedor as prov_mod
    from app.ia.local import ProveedorLocal

    d = db.execute(select(Deuda).where(Deuda.estado == "ACTIVA")).scalars().first()
    ag = admin.get("/api/agentes").json()[0]
    r = admin.post("/api/conversaciones", json={"id_agente": ag["id_agente"], "id_deuda": d.id_deuda, "canal": "TEXTO"})
    id_ll = r.json()["id_llamada"]
    prov_mod.establecer_proveedor(ProveedorLocal())
    try:
        texto = admin.post(f"/api/conversaciones/{id_ll}/mensajes", json={"texto": "Sí, soy yo"}).json()["respuesta"]
    finally:
        prov_mod.establecer_proveedor(None)
    aviso = motor.texto_herramienta(db, "dar_aviso_legal")[1] or motor.AVISO_LEGAL_DEFECTO
    assert aviso.split(".")[0].replace("{empresa}", "")[:20] in texto and "4 dígitos" in texto
    admin.post(f"/api/conversaciones/{id_ll}/finalizar")
    db.expire_all()
    assert db.get(Llamada, id_ll).estado_tecnico != "EN_CURSO"
