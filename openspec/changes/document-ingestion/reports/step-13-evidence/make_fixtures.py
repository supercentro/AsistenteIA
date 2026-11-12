"""Builds the group 13 fixtures (synthetic Spanish material and hostile files) into /out."""

import sys
import textwrap
from pathlib import Path

sys.path.insert(0, "/tests")
from pdf_support import (  # noqa: E402
    encrypted_pdf,
    pdf_from_streams,
    pdf_without_text,
    text_stream,
    truncated,
)

OUT = Path("/out")

TOPICS = {
    "calculo": (
        "Calculo diferencial",
        [
            "La derivada de una funcion mide su variacion instantanea en un punto concreto.",
            "Geometricamente, la derivada es la pendiente de la recta tangente a la curva.",
            "La regla de la cadena permite derivar funciones compuestas multiplicando derivadas.",
            "Un maximo local se encuentra donde la primera derivada se anula y la segunda es negativa.",
            "La integral definida calcula el area bajo una curva entre dos limites.",
            "El teorema fundamental del calculo relaciona derivacion e integracion.",
        ],
    ),
    "historia": (
        "Revolucion Francesa",
        [
            "La Revolucion Francesa comenzo en 1789 con la toma de la Bastilla en Paris.",
            "La Declaracion de los Derechos del Hombre y del Ciudadano proclamo la igualdad ante la ley.",
            "Luis XVI fue juzgado y ejecutado en la guillotina en enero de 1793.",
            "El periodo del Terror estuvo dirigido por Robespierre y el Comite de Salvacion Publica.",
            "Napoleon Bonaparte tomo el poder en 1799 mediante el golpe del 18 de Brumario.",
        ],
    ),
    "biologia": (
        "Fotosintesis",
        [
            "La fotosintesis es el proceso por el cual las plantas convierten la luz en energia quimica.",
            "Ocurre en los cloroplastos, donde la clorofila absorbe la luz solar.",
            "En la fase luminosa se produce oxigeno a partir de la ruptura de moleculas de agua.",
            "El ciclo de Calvin fija el dioxido de carbono y produce glucosa.",
            "La respiracion celular realiza el proceso inverso y libera energia en las mitocondrias.",
        ],
    ),
    "programacion": (
        "Estructuras de datos",
        [
            "Una pila es una estructura de datos que sigue el principio ultimo en entrar, primero en salir.",
            "Una cola atiende los elementos en el orden en que llegaron, primero en entrar, primero en salir.",
            "La busqueda binaria encuentra un elemento en un arreglo ordenado en tiempo logaritmico.",
            "Una tabla hash asocia claves con valores y ofrece acceso promedio en tiempo constante.",
            "Un arbol binario de busqueda mantiene los valores menores a la izquierda y los mayores a la derecha.",
        ],
    ),
}


def paragraphs(key: str, repeat: int) -> list[str]:
    title, sentences = TOPICS[key]
    out = [title]
    for i in range(repeat):
        out.append(" ".join(sentences[(i + j) % len(sentences)] for j in range(3)))
    return out


def write_text(name: str, keys: list[str], repeat: int, markdown: bool) -> None:
    blocks: list[str] = []
    for key in keys:
        paras = paragraphs(key, repeat)
        blocks.append(("# " if markdown else "") + paras[0])
        blocks.extend(paras[1:])
    (OUT / name).write_text("\n\n".join(blocks) + "\n", encoding="utf-8")


def write_pdf(name: str, keys: list[str], repeat: int) -> None:
    pages: list[bytes] = []
    for key in keys:
        paras = paragraphs(key, repeat)
        lines = [paras[0], ""]
        for para in paras[1:]:
            lines.extend(textwrap.wrap(para, 85))
            lines.append("")
        for start in range(0, len(lines), 40):
            pages.append(text_stream(lines[start : start + 40]))
    (OUT / name).write_bytes(pdf_from_streams(pages))


OUT.mkdir(exist_ok=True)
write_pdf("apuntes.pdf", ["calculo", "historia", "biologia", "programacion"], 6)
write_text("apuntes.txt", ["historia", "biologia"], 6, markdown=False)
write_text("apuntes.md", ["programacion", "calculo"], 6, markdown=True)
(OUT / "virus.exe").write_bytes(b"MZ" + b"\x90\x00" * 64)
(OUT / "grande.pdf").write_bytes(b"%PDF-1.4\n" + b"0" * (11 * 1024 * 1024))
(OUT / "vacio.txt").write_bytes(b"")
(OUT / "escaneado.pdf").write_bytes(pdf_without_text(3))
(OUT / "cifrado.pdf").write_bytes(encrypted_pdf(["Contenido protegido por contrasena."], user_password="clave"))
(OUT / "corrupto.pdf").write_bytes(truncated(pdf_from_streams([text_stream(["Documento cortado."] * 5)]), 0.5))
# A larger document to measure time and memory (about 600 KB of text).
write_text("extenso.txt", ["calculo", "historia", "biologia", "programacion"], 600, markdown=False)
for p in sorted(OUT.iterdir()):
    print(p.name, p.stat().st_size)
