"""Lee resultados.csv y dibuja el % de aciertos, errores y "no sé" por modo. Escribe grafico.png.

    uv run grafico.py
"""
import matplotlib.pyplot as plt
import pandas as pd

res = pd.read_csv("resultados.csv")
tabla = res.groupby("modo").resultado.value_counts(normalize=True).unstack(fill_value=0) * 100
tabla = tabla.reindex(columns=["acierta", "se equivoca", "no sabe"], fill_value=0)
orden = [m for m in ["memoria", "web", "mcp"] if m in tabla.index]
tabla = tabla.loc[orden]

ax = tabla.plot.barh(stacked=True, color=["#2e7d32", "#c62828", "#9e9e9e"], figsize=(8, 3.5))
for i, modo in enumerate(tabla.index):
    ax.text(101, i, f"{tabla.loc[modo, 'acierta']:.0f}% aciertos", va="center")
ax.set_xlim(0, 125)
ax.set_xlabel("% de las 10 preguntas")
ax.set_ylabel("")
ax.set_title("¿Acierta Claude 10 cifras del presupuesto público (MEF)?")
ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.22), ncol=3, fontsize=8, frameon=False)
plt.tight_layout()
plt.savefig("grafico.png", dpi=150)
print(tabla.round(1))
