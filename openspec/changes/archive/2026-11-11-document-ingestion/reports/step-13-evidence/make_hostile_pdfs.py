import sys
sys.path.insert(0, "/tests")
from pdf_support import pdf_many_pages, pdf_with_flate_stream
open("/out/trescientas_una_paginas.pdf", "wb").write(pdf_many_pages(301))
open("/out/bomba.pdf", "wb").write(pdf_with_flate_stream(2 * 1024**3))
