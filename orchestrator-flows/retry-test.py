class ScenarioReprocessor:

    def __init__(
        self,
        transformer_service,
        humanizer_service,
    ):
        self.transformer = transformer_service
        self.humanizer = humanizer_service

    def run(
        self,
        scenario,
        run_ia_transform,
        generate_single_bdd,
    ):

        print(
            f"\n🔄 Reprocessando cenário: "
            f"{scenario.name}"
        )

        success = run_ia_transform(
            scenario,
            self.transformer,
        )

        if not success:
            return

        generate_single_bdd(
            scenario,
            self.humanizer,
        )