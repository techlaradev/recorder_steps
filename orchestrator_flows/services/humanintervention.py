import tkinter as tk
from datetime import datetime
from playwright.sync_api import Page


class HumanIntervention:

    @classmethod
    def required(
        cls,
        page: Page,
        reason: str,
    ) -> None:

        timestamp = datetime.now().strftime(
            "%Y%m%d_%H%M%S"
        )

        page.screenshot(
            path=f"evidences/human_intervention_{timestamp}.png"
        )

        popup = tk.Tk()

        popup.title(
            "Intervenção Humana Necessária"
        )

        popup.geometry(
            "600x280"
        )

        popup.resizable(False, False)

        tk.Label(
            popup,
            text="🛑 Intervenção Humana Necessária",
            font=("Segoe UI", 14, "bold"),
        ).pack(
            pady=(20, 10)
        )

        tk.Label(
            popup,
            text=reason,
            wraplength=520,
            justify="left",
            font=("Segoe UI", 11),
        ).pack(
            padx=20,
            pady=10,
        )

        tk.Label(
            popup,
            text=(
                "Resolva a etapa manual e clique em "
                "'Continuar Teste'."
            ),
            font=("Segoe UI", 10),
        ).pack(
            pady=10
        )

        tk.Button(
            popup,
            text="✅ Continuar Teste",
            width=20,
            command=popup.destroy,
        ).pack(
            pady=20
        )

        popup.mainloop()

class HumanInterventionDetector:

    @staticmethod
    def needs_human(page) -> bool:

        checks = [
            'iframe[title*="reCAPTCHA"]',
            '.g-recaptcha',
            'iframe[src*="hcaptcha"]',
            'iframe[src*="turnstile"]'
        ]

        return any(
            page.locator(selector).count() > 0
            for selector in checks
        )