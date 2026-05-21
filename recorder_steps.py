import subprocess
import os

def main():
    print("=" * 30)
    print("🎥 Playwright Recorder Custom")
    print("=" * 30)

    # ✅ cria pasta flows automaticamente
    os.makedirs("flows", exist_ok=True)

    while True:
        nome = input("\nDigite o nome do arquivo (ENTER para sair): ").strip()
        if not nome:
            print("Saindo...")
            break

        url = input("Digite a URL para iniciar: ").strip()

        caminho = f"flows/{nome}.py"

        print("\n🔴 Abrindo Playwright...")
        print("(Feche a janela quando terminar a gravação)\n")

        try:
            subprocess.run(
                f"playwright codegen --target python -o {caminho} {url}",
                check=True,
                shell=True
            )

            print("\n✅ Script gerado:")
            print(f"- {caminho}")

        except subprocess.CalledProcessError:
            print("❌ Erro ao rodar Playwright")
            continue

        print("\n-------------------------------")

if __name__ == "__main__":
    main()
