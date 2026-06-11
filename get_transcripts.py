import json, sys, os
from youtube_transcript_api import YouTubeTranscriptApi

videos = [
    ("08ICdQh1mu0", "Entrevista_Completa"),
    ("TeGP4DNDKAg", "Entrevista_TV_Antiguo"),
    ("V7_EfGgcfVs", "Ser_o_no_ser_TVE"),
    ("Qj1DHBaLzoY", "Libro6_Meditacion_Autoalusiva"),
    ("NOhrcG0RqvU", "Psicofisiologia_Poder_Parte2"),
    ("gpaOcH_kgjQ", "Psicofisiologia_Poder_Parte1"),
    ("uWhWncIquuY", "Libro4_Fuerza_Vital"),
    ("Po24KP2AeFc", "Libro3_Conquista_Templo_parte1"),
    ("thOMfZGhMMI", "Libro3_Conquista_Templo_parte2"),
    ("xZSztLoX_o8", "Libro3_Conquista_Templo_parte1_alt"),
    ("bcT4xcLGDnc", "Libro2_Creacion_Experiencia"),
    ("jzjLcdwzdi4", "Estusha_Grinberg_Musica"),
    ("E9OSGOSwYNU", "Libro1_Teoria_Sintergica"),
    ("ZK_I2kgodR4", "Libro0_Viaje_Legado"),
    ("Y_VLd3OkcDs", "Bienvenidos_Canal"),
    ("JUqBy8N8P00", "Batalla_Templo_5"),
    ("pWa5dsaUt8Q", "Batalla_Templo_4"),
    ("ueGre1pwtrg", "Batalla_Templo_3"),
    ("SUr5VfQzY1s", "Batalla_Templo_2"),
    ("Asth1HunjEo", "Batalla_Templo_1"),
    ("U7zJDWBR9vM", "Coleccion_Chamanes_Mexico"),
]

out_dir = r"C:\test\grinberg_transcripts"
api = YouTubeTranscriptApi()
for vid, name in videos:
    try:
        tx = list(api.fetch(vid, languages=["es"]))
        path = os.path.join(out_dir, f"{vid}_{name}.txt")
        with open(path, "w", encoding="utf-8") as f:
            for t in tx:
                f.write(t.text + "\n")
        print(f"OK: {name} ({len(tx)} lines)")
    except Exception as e:
        err = str(e).split("\n")[0]
        print(f"FAIL: {name} - {err}")
