"""El contrato del servidor del MEF: si estas pruebas pasan, Claude Code y evaluar.py pueden usarlo.

    uv run pytest -q

Llaman al servidor en memoria, igual que lo haría Claude Code, y piden datos reales a Consulta Amigable.
Se usa el PIA porque no cambia durante el año (el PIM y el devengado cambian a diario).
"""
import asyncio
import json

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from server import mcp


async def _con_cliente(f):
    async with Client(mcp) as c:
        return await f(c)


def llamar(herramienta, **args):
    return asyncio.run(_con_cliente(lambda c: c.call_tool(herramienta, args))).data


def test_buscar_encuentra_salud():
    r = llamar("buscar_entidades", texto="salud")
    codigos = {(x["tipo"], x["codigo"]) for x in r}
    assert ("sector", "11") in codigos and ("pliego", "011") in codigos
    assert {"codigo", "nombre", "tipo", "nivel"} <= r[0].keys()


def test_cuatro_herramientas_como_minimo():
    nombres = {t.name for t in asyncio.run(_con_cliente(lambda c: c.list_tools()))}
    assert {"buscar_entidades", "ejecucion", "resumen"} <= nombres
    assert len(nombres) >= 4, "falta su herramienta propia"


def test_ejecucion_por_nivel():
    r = llamar("ejecucion", anio=2026, desagregar_por="nivel")
    filas = {f["codigo"]: f for f in r["filas"]}
    assert set(filas) == {"E", "M", "R"}
    assert filas["E"]["pia"] == 162305205072            # PIA 2026 del Gobierno Nacional
    assert r["fuente"].startswith("https://apps5.mineco.gob.pe")


def test_ejecucion_con_filtros():
    r = llamar("ejecucion", anio=2026, desagregar_por="pliego", nivel="E", sector="11")
    nombres = {f["codigo"]: f["nombre"] for f in r["filas"]}
    assert "SALUD" in nombres["011"]                     # en el sector 11, el pliego 011 es el Minsa
    assert r["filtros"] == {"nivel": "E", "sector": "11"}


def test_resumen_sin_cuentas_a_mano():
    r = llamar("resumen", anio=2026, desagregar_por="nivel")
    assert r["pia_total"] == 257561619143                # E + M + R
    assert 0 < r["avance_pct_total"] <= 100
    assert {"pim_total", "devengado_total", "mayor_avance", "menor_avance", "fuente"} <= r.keys()


def test_comparar_anios():
    r = llamar("comparar_anios", anio_a=2025, anio_b=2026, desagregar_por="nivel")
    assert len(r["filas"]) == 3
    assert all(f["variacion_pim_pct"] is not None for f in r["filas"])
    assert len(r["fuentes"]) == 2


def test_dimension_invalida_da_un_error_claro():
    with pytest.raises(ToolError, match="provincia"):
        llamar("ejecucion", anio=2026, desagregar_por="provincia")


def test_un_recurso():
    async def leer(c):
        assert len(await c.list_resource_templates()) >= 1
        return json.loads((await c.read_resource("mef://pliego/11/011"))[0].text)
    assert "SALUD" in asyncio.run(_con_cliente(leer))["nombre"]


def test_un_prompt():
    assert len(asyncio.run(_con_cliente(lambda c: c.list_prompts()))) >= 1


def test_filtrar_y_desagregar_por_lo_mismo():
    r = llamar("ejecucion", anio=2026, desagregar_por="pliego", nivel="E", sector="11", pliego="011")
    assert [f["codigo"] for f in r["filas"]] == ["011"]   # solo el Minsa, no todo el sector
