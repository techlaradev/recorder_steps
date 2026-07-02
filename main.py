from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import ia_prompting.humanizer_bdd as humanizer
import ia_prompting.code_perform_IA as transformer
import ia_prompting.client_ollama as ollama


# =============================
# 📦 MODELO DO FLUXO
# =============================
@dataclass
class Flow:
    name: str
    url: str
    base_dir: Path = Path("flows")

    @property
    def flow_dir(self) -> Path:
        return self.base_dir / self.name

    @property
    def raw_path(self) -> Path:
        return self.flow_dir / f"{self.name}.py"

    @property
    def clean_path(self) -> Path:
        return self.flow_dir / f"{self.name}_clean.py"

    @property
    def feature_path(self) -> Path:
        return self.flow_dir / f"{self.name}.feature"

    @property
    def evidences_dir(self) -> Path:
        return self.flow_dir / "evidences"

    @property
    def logs_dir(self) -> Path:
        return self.flow_dir / "logs"

    def ensure_dirs(self) -> None:
        self.flow_dir.mkdir(
            parents=True,
            exist_ok=True
        )

        self.evidences_dir.mkdir(
            exist_ok=True
        )

        self.logs_dir.mkdir(
            exist_ok=True
        )
# =============================
# 🎥 CODEGEN (Playwright)
# =============================
def run_codegen(flow: Flow) -> bool:
    try:
        print("\n➡️ Abrindo Playwright Codegen...")
        print("👉 Execute o fluxo no navegador")
        print("👉 Quando terminar, volte aqui e pressione ENTER")
        print(f"📁 Arquivo será salvo em: {flow.raw_path}\n")

        cmd = [
            sys.executable,
            "-m",
            "playwright",
            "codegen",
            "--target",
            "python",
            "-o",
            str(flow.raw_path),
            flow.url,
        ]

        # ✅ NÃO BLOQUEIA MAIS
        process = subprocess.Popen(cmd)

        # ✅ CONTROLE MANUAL
        input("\n👉 Pressione ENTER para encerrar o recorder...")

        print("🔪 Encerrando Playwright...")

        process.terminate()

        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            print("⚠️ Forçando encerramento...")
            process.kill()
            process.wait()

        print("✅ Codegen finalizado!")
        return True

    except Exception as e:
        print(f"❌ Erro ao rodar Playwright: {e}")
        return False


# =============================
# 🧠 IA — LIMPAR CÓDIGO
# =============================
def run_ia_transform(flow: Flow, transformer_service: transformer.StepTransformer) -> None:
    print("\n🧠 Iniciando processamento IA...\n")

    try:
        if not flow.raw_path.exists():
            print(f"❌ Arquivo não encontrado: {flow.raw_path}")
            return

        with flow.raw_path.open("r", encoding="utf-8") as f:
            code = f.read()

        print("➡️ filtrando código relevante...")

        lines = code.splitlines()
        filtered = [
            line for line in lines
            if "page." in line and "wait_for_timeout" not in line
        ]

        code_filtered = "\n".join(filtered).strip()

        if not code_filtered:
            print("⚠️ Nenhuma linha relevante encontrada para enviar à IA.")
            return

        code_filtered = code_filtered[:3000]

        print("➡️ enviando para IA...")
        clean_code = transformer_service.transform_to_playwright(code_filtered)

        with flow.clean_path.open("w", encoding="utf-8") as f:
            f.write(clean_code)

        print(f"✅ Código limpo salvo em: {flow.clean_path}")

    except Exception as e:
        print(f"❌ Erro na IA: {e}")


# =============================
# 📄 IA — GERAR BDD
# =============================
def run_bdd_generation(flow: Flow, humanizer_service: humanizer.Humanizer) -> None:
    print("\n📄 Gerando BDD...\n")

    try:
        # ✅ usa código limpo se existir
        source_path = flow.clean_path if flow.clean_path.exists() else flow.raw_path

        if not source_path.exists():
            print(f"❌ Arquivo não encontrado: {source_path}")
            return

        with source_path.open("r", encoding="utf-8") as f:
            code = f.read()

        print("➡️ enviando pra IA...")
        bdd = humanizer_service.steps_to_bdd(code)

        with flow.feature_path.open("w", encoding="utf-8") as f:
            f.write(bdd)

        print(f"✅ BDD salvo em: {flow.feature_path}")

    except Exception as e:
        print(f"❌ Erro ao gerar BDD: {e}")


# =============================
# 📝 INPUTS
# =============================
def ask_yes_no(message: str) -> bool:
    print(message)
    value = input("Digite 's' para sim ou 'n' para não: ").strip().lower()

    while value not in {"s", "n"}:
        value = input("Digite apenas 's' ou 'n': ").strip().lower()

    return value == "s"


def ask_flow() -> Flow | None:
    name = input("\nDigite o nome do fluxo (ENTER para sair): ").strip()
    if not name:
        return None

    url = input("Digite a URL para iniciar: ").strip()
    return Flow(name=name, url=url)


# =============================
# 🎯 MAIN
# =============================
def main() -> None:
    print("=" * 50)
    print("🎥 Playwright Recorder + IA + BDD")
    print("=" * 50)

    ollama_client = ollama.OllamaClient(
        model="mistral:7b-instruct"
    )

    transformer_service = transformer.StepTransformer(
        ollama_client
    )

    humaniz = humanizer.Humanizer(
        ollama_client
    )

    while True:
        flow = ask_flow()

        if flow is None:
            print("👋 Saindo...")
            break

        flow.ensure_dirs()

        print("\n📁 Estrutura criada:")
        print(f"📂 {flow.flow_dir}")
        print("   ├── evidences/")
        print("   └── logs/")

        print(f"\n📄 Recorder : {flow.raw_path}")
        print(f"📄 Feature  : {flow.feature_path}")

        # 🎥 Codegen
        if not run_codegen(flow):
            continue

        # 🧠 IA
        if ask_yes_no(
            "\n🧠 Deseja generalizar e limpar o código com IA?"
        ):
            run_ia_transform(
                flow,
                transformer_service
            )

        # 📄 BDD
        if ask_yes_no(
            "\n📄 Deseja gerar BDD?"
        ):
            run_bdd_generation(
                flow,
                humaniz
            )

        print("\n✅ Fluxo finalizado!")
        print(f"📂 Pasta do fluxo: {flow.flow_dir}")


if __name__ == "__main__":
    main()