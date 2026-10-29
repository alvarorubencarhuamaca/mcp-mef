"""Servidor MCP de Consulta Amigable del MEF: ejecución del presupuesto público del Perú.

    uv run pytest -q                                        # las pruebas
    uv run server.py                                        # el servidor, por stdio
    claude mcp add --scope project mef -- uv run server.py  # conectarlo a Claude Code

Las cuentas las hace Python, no el modelo: cada cifra sale de una consulta que se puede repetir.
"""
import unicodedata
from functools import cache
from io import StringIO

import httpx
import pandas as pd
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

URL_MEF = "https://apps5.mineco.gob.pe/transparencia/Navegador/Navegar_7.aspx"
COLUMNAS = ["nombre", "pia", "pim", "certificacion", "compromiso_anual",
            "atencion_compromiso_mensual", "devengado", "girado", "avance_pct"]
# Cada "botón" de Consulta Amigable es un número en la URL. El orden importa: es la jerarquía.
DIMENSIONES = {"nivel": "1", "sector": "2", "pliego": "3", "funcion": "8", "fuente": "14",
               "departamento": "21", "mes": "23", "generica": "24"}
SOLO_LECTURA = {"readOnlyHint": True, "openWorldHint": True}

mcp = FastMCP("mef", instructions=(
    "Ejecución presupuestal del Estado peruano (Consulta Amigable del MEF), en soles. "
    "Si no conoces el código de una entidad, búscalo primero con buscar_entidades; luego usa ejecucion. "
    "No calcules a mano: cita siempre el año, los filtros y la fuente de cada cifra."))


def _sin_tildes(s):
    return unicodedata.normalize("NFD", str(s).lower()).encode("ascii", "ignore").decode()


def _filtros(**dados):
    """Arma los filtros en orden de jerarquía y sin los que vienen vacíos."""
    return tuple((d, v) for d in DIMENSIONES if (v := dados.get(d)))


def _tabla(anio, desagregar_por, dados):
    """Consulta al MEF. Si se filtra y desagrega por lo mismo (pliego="011" y desagregar_por="pliego"),
    pide la tabla sin ese filtro y se queda solo con esa fila: en la URL ambos usan el mismo parámetro."""
    if desagregar_por not in DIMENSIONES:
        raise ToolError(f"desagregar_por debe ser uno de {list(DIMENSIONES)}, no {desagregar_por!r}.")
    dados = dict(dados)
    misma = dados.pop(desagregar_por, None)
    df, fuente = _consultar(anio, desagregar_por, _filtros(**dados))
    if misma:
        df = df[df["codigo"] == misma]
        if df.empty:
            raise ToolError(f"No hay {desagregar_por} {misma!r} con esos filtros. Búsquenlo con buscar_entidades.")
    return df, fuente


@cache
def _consultar(anio: int, desagregar_por: str, filtros: tuple) -> tuple[pd.DataFrame, str]:
    """Pide una tabla al MEF. filtros = (("nivel", "E"), ("sector", "10")). Se guarda en caché."""
    params = {"y": str(anio)}
    for dim, valor in filtros:
        params[DIMENSIONES[dim]] = valor
    params[DIMENSIONES[desagregar_por]] = ""          # el vacío, al final: "desagrega por esto"

    r = httpx.get(URL_MEF, params=params, timeout=60, headers={"User-Agent": "Mozilla/5.0"})
    try:
        df = pd.read_html(StringIO(r.text), attrs={"class": "Data"})[0]
    except ValueError:
        raise ToolError(f"El MEF no devolvió datos para {dict(filtros)} en {anio}. Revisen los códigos.")
    df = df.iloc[:, 1:]
    df.columns = COLUMNAS
    partes = df["nombre"].str.split(": ", n=1, expand=True)
    df.insert(0, "codigo", partes[0].str.strip())
    df["nombre"] = partes[1].str.strip()
    return df, str(r.url)


@mcp.tool(annotations=SOLO_LECTURA)
def ejecucion(anio: int, desagregar_por: str, nivel: str | None = None, sector: str | None = None,
              pliego: str | None = None, departamento: str | None = None,
              generica: str | None = None) -> dict:
    """Ejecución del presupuesto (PIA, PIM, certificado, devengado, girado y avance %) en soles.

    desagregar_por: "nivel", "sector", "pliego", "funcion", "fuente", "departamento", "mes" o "generica".
    Filtros opcionales (códigos de Consulta Amigable): nivel "E" (nacional), "R" (regional) o "M" (local);
    sector de 2 dígitos ("10" = Educación); pliego de 3 dígitos (sector "11" + pliego "011" = Ministerio de Salud);
    departamento de 2 dígitos ("15" = Lima); generica como "2-3" (bienes y servicios).
    Ejemplo: ejecucion(2026, "pliego", nivel="E", sector="10") = los pliegos del sector Educación.
    Si filtras por pliego, pasa también su sector: el mismo código de pliego se repite en varios sectores.
    """
    dados = dict(nivel=nivel, sector=sector, pliego=pliego, departamento=departamento, generica=generica)
    df, fuente = _tabla(anio, desagregar_por, dados)
    return {"anio": anio, "filtros": {k: v for k, v in dados.items() if v}, "desagregado_por": desagregar_por,
            "filas": df.to_dict("records"), "fuente": fuente}


@mcp.tool(annotations=SOLO_LECTURA)
def buscar_entidades(texto: str, anio: int = 2026) -> list[dict]:
    """Busca sectores y pliegos (ministerios, gobiernos regionales, etc.) por nombre.

    Todas las palabras deben aparecer en el nombre; las tildes no importan.
    Ejemplos: "salud", "educacion", "gobierno regional cusco", "interior".
    Devuelve el tipo (sector o pliego), el nivel y el código que piden los filtros de ejecucion.
    """
    partes = []
    for nivel in ("E", "R"):
        for tipo in ("sector", "pliego"):
            df, _ = _consultar(anio, tipo, (("nivel", nivel),))
            partes.append(df[["codigo", "nombre"]].assign(tipo=tipo, nivel=nivel))
    todo = pd.concat(partes).drop_duplicates()
    m = pd.Series(True, index=todo.index)
    for palabra in _sin_tildes(texto).split():
        m &= todo["nombre"].map(_sin_tildes).str.contains(palabra, regex=False)
    return todo[m].head(15).to_dict("records")


@mcp.tool(annotations=SOLO_LECTURA)
def resumen(anio: int, desagregar_por: str, nivel: str | None = None, sector: str | None = None,
            pliego: str | None = None, departamento: str | None = None) -> dict:
    """Totales y extremos de una consulta, para no sumar ni dividir a mano.

    Devuelve el PIA, PIM y devengado totales, el avance % total (devengado / PIM),
    las 3 filas con más PIM y las de mayor y menor avance. Mismos argumentos que ejecucion.
    Ejemplo: resumen(2026, "departamento", nivel="R") = qué región gasta más rápido y cuál más lento.
    """
    df, fuente = _tabla(anio, desagregar_por, dict(nivel=nivel, sector=sector, pliego=pliego,
                                                   departamento=departamento))
    con_pim = df[df["pim"] > 0]
    fila = lambda r: {"codigo": r["codigo"], "nombre": r["nombre"], "pim": int(r["pim"]),
                      "avance_pct": float(r["avance_pct"])}
    return {
        "anio": anio, "desagregado_por": desagregar_por, "filas": len(df),
        "pia_total": int(df["pia"].sum()), "pim_total": int(df["pim"].sum()),
        "devengado_total": int(df["devengado"].sum()),
        "avance_pct_total": round(100 * df["devengado"].sum() / df["pim"].sum(), 1),
        "mas_presupuesto": [fila(r) for _, r in df.nlargest(3, "pim").iterrows()],
        "mayor_avance": fila(con_pim.loc[con_pim["avance_pct"].idxmax()]),
        "menor_avance": fila(con_pim.loc[con_pim["avance_pct"].idxmin()]),
        "fuente": fuente,
    }


@mcp.tool(annotations=SOLO_LECTURA)
def comparar_anios(anio_a: int, anio_b: int, desagregar_por: str = "nivel", nivel: str | None = None,
                   sector: str | None = None, pliego: str | None = None) -> dict:
    """Compara el PIM y el devengado de dos años (2024 en adelante), fila por fila, con su variación %.

    Úsala para preguntas como "¿cuánto más presupuesto tiene Salud que el año pasado?".
    Ojo: si uno de los años está en curso, su devengado aún no está completo.
    Ejemplo: comparar_anios(2025, 2026, "pliego", nivel="E", sector="11").
    """
    f = _filtros(nivel=nivel, sector=sector, pliego=pliego)
    a, fuente_a = _consultar(anio_a, desagregar_por, f)
    b, fuente_b = _consultar(anio_b, desagregar_por, f)
    m = a.merge(b, on="codigo", suffixes=(f"_{anio_a}", f"_{anio_b}"))
    filas = []
    for _, r in m.iterrows():
        pim_a, pim_b = r[f"pim_{anio_a}"], r[f"pim_{anio_b}"]
        filas.append({"codigo": r["codigo"], "nombre": r[f"nombre_{anio_b}"],
                      f"pim_{anio_a}": int(pim_a), f"pim_{anio_b}": int(pim_b),
                      "variacion_pim_pct": round(100 * (pim_b / pim_a - 1), 1) if pim_a else None,
                      f"avance_{anio_a}": float(r[f"avance_pct_{anio_a}"]),
                      f"avance_{anio_b}": float(r[f"avance_pct_{anio_b}"])})
    return {"filas": filas, "fuentes": [fuente_a, fuente_b]}


@mcp.resource("mef://pliego/{sector}/{pliego}")
def ficha_pliego(sector: str, pliego: str) -> dict:
    """Ficha de un pliego en 2026. El pliego solo es único junto con su sector: 11/011 = Ministerio de Salud."""
    for nivel in ("E", "R"):
        df, fuente = _consultar(2026, "pliego", (("nivel", nivel), ("sector", sector)))
        fila = df[df["codigo"] == pliego]
        if not fila.empty:
            r = fila.iloc[0]
            return {"sector": sector, "pliego": pliego, "nombre": r["nombre"], "nivel": nivel, "anio": 2026,
                    "pim": int(r["pim"]), "devengado": int(r["devengado"]),
                    "avance_pct": float(r["avance_pct"]), "fuente": fuente}
    raise ToolError(f"No existe el pliego {pliego!r} en el sector {sector!r}. Búsquenlo con buscar_entidades.")


@mcp.prompt
def informe_ejecucion(entidad: str) -> str:
    """Pide un informe corto de ejecución presupuestal de una entidad."""
    return (f"Escribe un informe breve sobre la ejecución presupuestal de {entidad} en 2026. "
            "1) Busca su código con buscar_entidades. 2) Usa resumen y ejecucion para el PIM, el devengado "
            "y el avance %, y comparar_anios contra 2025. 3) Cita el año, los filtros y la fuente de cada cifra. "
            "No calcules nada a mano: si una cifra no sale de una herramienta, no la pongas.")


if __name__ == "__main__":
    mcp.run()