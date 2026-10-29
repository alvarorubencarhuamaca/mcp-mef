# MCP del MEF · Consulta Amigable

Servidor MCP (FastMCP 4) con la ejecución del presupuesto público del Perú: PIA, PIM, devengado y avance % por nivel de
gobierno, sector, pliego, departamento o genérica. Los datos vienen de
[Consulta Amigable](https://apps5.mineco.gob.pe/transparencia/Navegador/default.aspx) y cada respuesta trae la URL de
origen. El informe con la evaluación está en [`informe.md`](informe.md).

```bash
uv run pytest -q                       # 10 pruebas con datos reales
claude                                 # .mcp.json ya conecta los servidores mef y fetch
uv run evaluar.py --modos memoria web mcp
uv run grafico.py
```

| Archivo | Qué es |
|---|---|
| `server.py` | 4 herramientas (`buscar_entidades`, `ejecucion`, `resumen`, `comparar_anios`), el recurso `mef://pliego/{sector}/{pliego}` y el prompt `informe_ejecucion` |
| `test_server.py` | 10 pruebas |
| `preguntas.csv` | 10 preguntas con la cifra oficial y su tolerancia |
| `evaluar.py` | Hace cada pregunta a Claude (`claude -p`) en modo memoria, web y MCP, y califica |
| `resultados.csv`, `resultados_base.csv` | Corridas de la evaluación |
| `grafico.py`, `grafico.png` | Porcentaje de aciertos por modo |

Basado en la sesión 04 de [d2cml-ai/Data-Science-Python](https://github.com/d2cml-ai/Data-Science-Python/tree/main/sessions/04-mcp-claude-code).
