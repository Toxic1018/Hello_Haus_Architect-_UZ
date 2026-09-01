"""
Zamonaviy Kalkulyator
----------------------
Python + tkinter yordamida yaratilgan, qorong'i (dark mode) uslubidagi
zamonaviy kalkulyator dasturi.

Ishga tushirish:
    python kalkulyator.py
"""

import tkinter as tk
from tkinter import font as tkfont


# ---------- Ranglar palitrasi (zamonaviy dark theme) ----------
BG_COLOR = "#1e1e2e"          # asosiy fon
DISPLAY_BG = "#181825"        # ekran foni
DISPLAY_FG = "#ffffff"        # ekran matni
BTN_NUMBER_BG = "#313244"     # raqam tugmalari
BTN_NUMBER_FG = "#ffffff"
BTN_OPERATOR_BG = "#fab387"   # amal tugmalari (+ - * /)
BTN_OPERATOR_FG = "#1e1e2e"
BTN_FUNCTION_BG = "#585b70"   # C, ⌫, %, () kabi funksiyalar
BTN_FUNCTION_FG = "#ffffff"
BTN_EQUAL_BG = "#a6e3a1"      # = tugmasi
BTN_EQUAL_FG = "#1e1e2e"
BTN_ACTIVE_LIGHTEN = "#45475a"


class ZamonaviyKalkulyator:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Zamonaviy Kalkulyator")
        self.root.configure(bg=BG_COLOR)
        self.root.resizable(False, False)

        # Ifoda (foydalanuvchi kiritayotgan matn)
        self.ifoda = ""

        # Shriftlar
        self.display_font = tkfont.Font(family="Segoe UI", size=32, weight="bold")
        self.small_font = tkfont.Font(family="Segoe UI", size=14)
        self.btn_font = tkfont.Font(family="Segoe UI", size=18, weight="bold")

        self._ekran_yasash()
        self._tugmalar_yasash()

        # Klaviatura orqali ham foydalanish mumkin
        self.root.bind("<Key>", self._klaviatura_bosildi)

    # ---------- Ekran (display) qismi ----------
    def _ekran_yasash(self):
        ekran_frame = tk.Frame(self.root, bg=DISPLAY_BG, height=140)
        ekran_frame.grid(row=0, column=0, columnspan=4, sticky="nsew")
        ekran_frame.grid_propagate(False)

        # Kichik tarix qatori (kiritilayotgan to'liq ifoda)
        self.tarix_label = tk.Label(
            ekran_frame, text="", anchor="e",
            bg=DISPLAY_BG, fg="#9399b2", font=self.small_font
        )
        self.tarix_label.pack(fill="x", padx=20, pady=(15, 0))

        # Asosiy natija qatori
        self.natija_var = tk.StringVar(value="0")
        self.natija_label = tk.Label(
            ekran_frame, textvariable=self.natija_var, anchor="e",
            bg=DISPLAY_BG, fg=DISPLAY_FG, font=self.display_font
        )
        self.natija_label.pack(fill="x", padx=20, pady=(0, 15))

    # ---------- Tugmalar paneli ----------
    def _tugmalar_yasash(self):
        panel = tk.Frame(self.root, bg=BG_COLOR)
        panel.grid(row=1, column=0, sticky="nsew")

        # Tugmalar tartibi: (matn, turi)
        # turi: "func" (C, ⌫, %, () ), "op" (+ - * /), "eq" (=), "num" (raqamlar/nuqta)
        tugmalar = [
            [("C", "func"), ("⌫", "func"), ("%", "func"), ("÷", "op")],
            [("7", "num"), ("8", "num"), ("9", "num"), ("×", "op")],
            [("4", "num"), ("5", "num"), ("6", "num"), ("−", "op")],
            [("1", "num"), ("2", "num"), ("3", "num"), ("+", "op")],
            [("±", "func"), ("0", "num"), (",", "num"), ("=", "eq")],
        ]

        for satr_idx, satr in enumerate(tugmalar):
            for ust_idx, (matn, tur) in enumerate(satr):
                self._tugma_yarat(panel, matn, tur, satr_idx, ust_idx)

        for i in range(4):
            panel.grid_columnconfigure(i, weight=1)
        for i in range(len(tugmalar)):
            panel.grid_rowconfigure(i, weight=1)

    def _tugma_yarat(self, panel, matn, tur, satr, ustun):
        ranglar = {
            "num": (BTN_NUMBER_BG, BTN_NUMBER_FG),
            "op": (BTN_OPERATOR_BG, BTN_OPERATOR_FG),
            "func": (BTN_FUNCTION_BG, BTN_FUNCTION_FG),
            "eq": (BTN_EQUAL_BG, BTN_EQUAL_FG),
        }
        bg, fg = ranglar[tur]

        btn = tk.Button(
            panel, text=matn, font=self.btn_font,
            bg=bg, fg=fg, bd=0, relief="flat",
            activebackground=BTN_ACTIVE_LIGHTEN, activeforeground=fg,
            width=4, height=2, cursor="hand2",
            command=lambda m=matn, t=tur: self._tugma_bosildi(m, t)
        )
        btn.grid(row=satr, column=ustun, padx=6, pady=6, sticky="nsew", ipady=6)

        # Ustiga sichqoncha kelganda ozgina yorishtirish effekti
        def kirish(e, b=btn, asl_bg=bg):
            b.configure(bg=self._yoritish(asl_bg))

        def chiqish(e, b=btn, asl_bg=bg):
            b.configure(bg=asl_bg)

        btn.bind("<Enter>", kirish)
        btn.bind("<Leave>", chiqish)

    @staticmethod
    def _yoritish(hex_rang, koeffitsient=0.15):
        """Rangni ozgina ochroq qilish (hover effekti uchun)."""
        hex_rang = hex_rang.lstrip("#")
        r, g, b = (int(hex_rang[i:i + 2], 16) for i in (0, 2, 4))
        r = min(255, int(r + (255 - r) * koeffitsient))
        g = min(255, int(g + (255 - g) * koeffitsient))
        b = min(255, int(b + (255 - b) * koeffitsient))
        return f"#{r:02x}{g:02x}{b:02x}"

    # ---------- Mantiq (logic) qismi ----------
    def _tugma_bosildi(self, matn, tur):
        if tur == "func":
            if matn == "C":
                self.ifoda = ""
            elif matn == "⌫":
                self.ifoda = self.ifoda[:-1]
            elif matn == "%":
                self.ifoda += "%"
            elif matn == "±":
                self._ishorani_almashtirish()
        elif tur in ("num", "op"):
            belgi = {"×": "*", "÷": "/", "−": "-", ",": "."}.get(matn, matn)
            self.ifoda += belgi
        elif tur == "eq":
            self._hisoblash()

        self._ekranni_yangilash()

    def _ishorani_almashtirish(self):
        """Oxirgi kiritilgan sonning ishorasini almashtiradi."""
        if not self.ifoda:
            return
        # Oddiy holat: butun ifodani -(...) ga o'raymiz
        if self.ifoda.startswith("-("):
            self.ifoda = self.ifoda[2:-1]
        else:
            self.ifoda = f"-({self.ifoda})"

    def _hisoblash(self):
        if not self.ifoda:
            return
        try:
            xavfsiz_ifoda = self.ifoda.replace("%", "/100")
            # Faqat xavfsiz belgilarga ruxsat beramiz
            ruxsat_etilgan = set("0123456789.+-*/()%")
            if not set(self.ifoda) <= ruxsat_etilgan:
                raise ValueError("Noto'g'ri belgi")

            natija = eval(xavfsiz_ifoda)  # noqa: S307 - faqat sonlar/amallar filtrlangan
            if isinstance(natija, float) and natija.is_integer():
                natija = int(natija)
            self.tarix_label.config(text=self.ifoda + " =")
            self.ifoda = str(natija)
        except (ZeroDivisionError, SyntaxError, ValueError):
            self.natija_var.set("Xatolik")
            self.ifoda = ""
            return

    def _ekranni_yangilash(self):
        self.natija_var.set(self.ifoda if self.ifoda else "0")
        if not self.ifoda:
            self.tarix_label.config(text="")

    # ---------- Klaviatura bilan boshqarish ----------
    def _klaviatura_bosildi(self, event):
        raqamlar_va_amallar = "0123456789+-*/().%"
        bosilgan = event.char

        if bosilgan in raqamlar_va_amallar:
            self.ifoda += bosilgan
            self._ekranni_yangilash()
        elif bosilgan == "," :
            self.ifoda += "."
            self._ekranni_yangilash()
        elif event.keysym == "Return":
            self._hisoblash()
            self._ekranni_yangilash()
        elif event.keysym == "BackSpace":
            self.ifoda = self.ifoda[:-1]
            self._ekranni_yangilash()
        elif event.keysym == "Escape":
            self.ifoda = ""
            self._ekranni_yangilash()


def main():
    root = tk.Tk()
    app = ZamonaviyKalkulyator(root)
    root.mainloop()


if __name__ == "__main__":
    main()
