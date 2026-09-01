"""
Aqlli Zamonaviy Qo'l Soati (Smart Watch Simulyatsiyasi)
---------------------------------------------------------
Python + tkinter yordamida yaratilgan, dumaloq ekranli aqlli soat interfeysi.
Vaqt, sana, batareya darajasi va qadamlar sonini ko'rsatadi.

Ishga tushirish:
    python aqlli_soat.py
"""

import tkinter as tk
from tkinter import font as tkfont
from datetime import datetime
import math
import random


# ---------- Ranglar palitrasi ----------
FON_RANG = "#0d0d0d"          # tashqi fon (qorong'i xona)
SOAT_KORPUS = "#1a1a1a"       # soat korpusi (band qismi)
EKRAN_FON = "#000000"         # AMOLED ekran foni
HALQA_RANG = "#2a2a2a"        # soat ramkasi
AKSENT_RANG = "#00e5ff"       # asosiy aksent (moviy-neon)
IKKINCHI_AKSENT = "#ff6b6b"   # qadamlar uchun
UCHINCHI_AKSENT = "#7bed9f"   # batareya uchun
MATN_RANG = "#ffffff"
XIRA_MATN = "#7a7a7a"


class AqlliSoat:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Aqlli Qo'l Soati")
        self.root.configure(bg=FON_RANG)
        self.root.resizable(False, False)

        # Simulyatsiya qilingan sensor ma'lumotlari
        self.batareya = 78          # foizda
        self.qadamlar = 4213
        self.yurak_urishi = 72       # bpm
        self.rejim = "vaqt"          # "vaqt" yoki "salomatlik" oynasi almashadi

        # Shriftlar
        self.vaqt_font = tkfont.Font(family="Segoe UI", size=40, weight="bold")
        self.sana_font = tkfont.Font(family="Segoe UI", size=13)
        self.mayda_font = tkfont.Font(family="Segoe UI", size=11)
        self.katta_font = tkfont.Font(family="Segoe UI", size=22, weight="bold")

        self._korpus_yasash()
        self._boshqaruv_tugmalari()

        # Ekranga bosilganda rejim almashadi
        self.canvas.bind("<Button-1>", self._rejimni_almashtirish)

        self._yangilash()

    # ---------- Soat korpusi va dumaloq ekran ----------
    def _korpus_yasash(self):
        o_lchov = 380
        self.canvas = tk.Canvas(
            self.root, width=o_lchov, height=o_lchov,
            bg=FON_RANG, highlightthickness=0
        )
        self.canvas.pack(padx=30, pady=(30, 10))

        markaz = o_lchov // 2
        self.markaz = markaz

        # Tashqi korpus (band bilan tutashuvchi qismi)
        self.canvas.create_oval(10, 10, o_lchov - 10, o_lchov - 10,
                                 fill=SOAT_KORPUS, outline=HALQA_RANG, width=6)
        # Ichki ekran (AMOLED qora ekran)
        self.ekran_radius = markaz - 35
        self.canvas.create_oval(
            markaz - self.ekran_radius, markaz - self.ekran_radius,
            markaz + self.ekran_radius, markaz + self.ekran_radius,
            fill=EKRAN_FON, outline=AKSENT_RANG, width=2
        )

        # Band (soat kamari) - yuqori va pastki qismi
        self.canvas.create_rectangle(markaz - 45, 0, markaz + 45, 15,
                                      fill=SOAT_KORPUS, outline="")
        self.canvas.create_rectangle(markaz - 45, o_lchov - 15, markaz + 45, o_lchov,
                                      fill=SOAT_KORPUS, outline="")

        # Dinamik matnlar uchun bo'sh identifikatorlar (keyin yangilanadi)
        self.soat_matn_id = None
        self.sana_matn_id = None
        self.holat_elementlari = []

    # ---------- Pastki boshqaruv tugmalari ----------
    def _boshqaruv_tugmalari(self):
        panel = tk.Frame(self.root, bg=FON_RANG)
        panel.pack(pady=(0, 20))

        info = tk.Label(
            panel, text="Ekranga bosing: Vaqt ⇄ Salomatlik rejimi",
            bg=FON_RANG, fg=XIRA_MATN, font=self.mayda_font
        )
        info.pack()

    def _rejimni_almashtirish(self, event=None):
        self.rejim = "salomatlik" if self.rejim == "vaqt" else "vaqt"
        self._chizish()

    # ---------- Ekran mazmunini chizish ----------
    def _chizish(self):
        # Avvalgi dinamik elementlarni tozalash (korpus va halqalarni saqlab qolamiz)
        self.canvas.delete("dinamik")

        if self.rejim == "vaqt":
            self._vaqt_oynasi_chizish()
        else:
            self._salomatlik_oynasi_chizish()

    def _vaqt_oynasi_chizish(self):
        hozir = datetime.now()
        vaqt_matni = hozir.strftime("%H:%M")
        sekund_matni = hozir.strftime("%S")
        sana_matni = hozir.strftime("%A, %d-%B")

        m = self.markaz

        # Tashqi progress-halqa (kunlik faollik maqsadiga nisbatan, simulyatsiya)
        progress = min(self.qadamlar / 8000, 1.0)
        self.canvas.create_arc(
            m - self.ekran_radius + 8, m - self.ekran_radius + 8,
            m + self.ekran_radius - 8, m + self.ekran_radius - 8,
            start=90, extent=-360 * progress,
            outline=AKSENT_RANG, width=5, style="arc", tags="dinamik"
        )

        # Asosiy vaqt
        self.canvas.create_text(
            m, m - 25, text=vaqt_matni, fill=MATN_RANG,
            font=self.vaqt_font, tags="dinamik"
        )
        # Sekundlar (kichikroq, yonida)
        self.canvas.create_text(
            m, m + 10, text=f":{sekund_matni}", fill=AKSENT_RANG,
            font=self.sana_font, tags="dinamik"
        )
        # Sana
        self.canvas.create_text(
            m, m + 40, text=sana_matni, fill=XIRA_MATN,
            font=self.mayda_font, tags="dinamik"
        )
        # Batareya (yuqorida, kichik belgi bilan)
        self.canvas.create_text(
            m, m - 90, text=f"🔋 {self.batareya}%", fill=UCHINCHI_AKSENT,
            font=self.mayda_font, tags="dinamik"
        )

    def _salomatlik_oynasi_chizish(self):
        m = self.markaz

        self.canvas.create_text(
            m, m - 95, text="SALOMATLIK", fill=XIRA_MATN,
            font=self.mayda_font, tags="dinamik"
        )

        # Yurak urishi
        self.canvas.create_text(
            m, m - 55, text=f"♥ {self.yurak_urishi}", fill=IKKINCHI_AKSENT,
            font=self.katta_font, tags="dinamik"
        )
        self.canvas.create_text(
            m, m - 25, text="bpm", fill=XIRA_MATN,
            font=self.mayda_font, tags="dinamik"
        )

        # Qadamlar
        self.canvas.create_text(
            m, m + 15, text=f"👣 {self.qadamlar}", fill=AKSENT_RANG,
            font=self.katta_font, tags="dinamik"
        )
        self.canvas.create_text(
            m, m + 45, text="qadam", fill=XIRA_MATN,
            font=self.mayda_font, tags="dinamik"
        )

        # Batareya
        self.canvas.create_text(
            m, m + 80, text=f"🔋 {self.batareya}%", fill=UCHINCHI_AKSENT,
            font=self.mayda_font, tags="dinamik"
        )

    # ---------- Simulyatsiya: har soniyada ma'lumotlarni yangilash ----------
    def _yangilash(self):
        # Yurak urishini va qadamlarni tabiiy tebranish bilan simulyatsiya qilamiz
        self.yurak_urishi = max(60, min(100, self.yurak_urishi + random.randint(-1, 1)))
        if random.random() < 0.3:
            self.qadamlar += random.randint(0, 3)
        if random.random() < 0.02 and self.batareya > 0:
            self.batareya -= 1

        self._chizish()
        self.root.after(1000, self._yangilash)


def main():
    root = tk.Tk()
    app = AqlliSoat(root)
    root.mainloop()


if __name__ == "__main__":
    main()
