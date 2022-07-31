from time import time
from types import ModuleType
from typing import Callable, Dict, Type
import numpy as np
from openfisca_core.taxbenefitsystems import TaxBenefitSystem
from openfisca_core.simulation_builder import SimulationBuilder
from openfisca_core.model_api import Enum
from openfisca_core.reforms import Reform
from policyengine.country.openfisca.entities import build_entities
from policyengine.country.openfisca.parameters import build_parameters
from policyengine.country.openfisca.reforms import apply_reform, PolicyReform
from policyengine.country.openfisca.variables import build_variables
from policyengine.country.results_config import PolicyEngineResultsConfig
from policyengine.web_server.cache import PolicyEngineCache, cached_endpoint
from policyengine.web_server.logging import PolicyEngineLogger
import dpath
from policyengine.impact.population.charts import (
    decile_chart,
    inequality_chart,
    intra_decile_chart,
    poverty_chart,
    waterfall_chart,
)
from policyengine.impact.population.metrics import headline_metrics


class PolicyEngineCountry:
    """Base class for a PolicyEngine country. Each country has a set of API endpoints available."""

    api_endpoints: Dict[str, Callable] = None
    """The API endpoints available for this country.
    """

    name: str = None
    """The name of the country.
    """

    openfisca_country_model: ModuleType = None
    """The OpenFisca country model for this country.
    """

    default_reform: Reform = None
    """An OpenFisca reform to apply to the country model before use.
    """

    results_config: Type[PolicyEngineResultsConfig] = None
    """The results configuration for this country. Used to interface with the OpenFisca country model.
    """

    def __init__(self):
        self.api_endpoints = dict(
            entities=self.entities,
            variables=self.variables,
            parameters=self.parameters,
            parameter=self.parameter,
            budgetary_impact=self.budgetary_impact,
            calculate=self.calculate,
            population_reform=self.population_reform,
            population_reform_runtime=self.population_reform_runtime,
        )
        if self.name is None:
            self.name = self.__class__.__name__.lower()
        if self.openfisca_country_model is None:
            raise ValueError("No OpenFisca country model specified.")
        (
            self.tax_benefit_system_type,
            self.microsimulation_type,
            self.individualsim_type,
        ) = map(
            lambda name: getattr(self.openfisca_country_model, name),
            ("CountryTaxBenefitSystem", "Microsimulation", "IndividualSim"),
        )
        self.tax_benefit_system = self.tax_benefit_system_type()
        self.baseline_tax_benefit_system = self.tax_benefit_system_type()
        if self.default_reform is not None:
            apply_reform(self.default_reform, self.tax_benefit_system)

        self.entity_data = build_entities(self.tax_benefit_system)
        self.variable_data = build_variables(self.tax_benefit_system)
        self.parameter_data = build_parameters(self.tax_benefit_system)

        self.baseline_microsimulation = None

        self.population_reform_recent_calls = dict(
            reform_only=[10],
            reform_and_baseline=[10],
        )

    def create_reform(self, parameters: dict) -> PolicyReform:
        """Generate an OpenFisca reform from PolicyEngine parameters.

        Args:
            parameters (dict): The PolicyEngine parameters.

        Returns:
            Reform: The OpenFisca reform.
        """
        return PolicyReform(
            parameters, self.parameter_data, default_reform=self.default_reform
        )

    def create_microsimulations(self, parameters: dict) -> Reform:
        """Generate an OpenFisca reform from PolicyEngine parameters.

        Args:
            parameters (dict): The PolicyEngine parameters.

        Returns:
            Reform: The OpenFisca reform.
        """
        policy_reform = self.create_reform(parameters)
        if (
            not policy_reform.edits_baseline
            and self.baseline_microsimulation is None
        ):
            baseline = (
                self.baseline_microsimulation
            ) = self.microsimulation_type(self.default_reform)
        elif policy_reform.edits_baseline:
            baseline = self.microsimulation_type(policy_reform.baseline)
        else:
            baseline = self.baseline_microsimulation
        reformed = self.microsimulation_type(policy_reform.reform)
        return baseline, reformed

    def entities(self, params: dict, logger: PolicyEngineLogger) -> dict:
        """Get the available entities for the OpenFisca country model."""
        return self.entity_data

    def variables(self, params: dict, logger: PolicyEngineLogger) -> dict:
        """Get the available entities for the OpenFisca country model."""
        return self.variable_data

    def parameters(self, params: dict, logger: PolicyEngineLogger) -> dict:
        """Get the available entities for the OpenFisca country model."""
        if "policy_date" in params:
            return build_parameters(
                self.baseline_tax_benefit_system,
                date=params.get("policy_date"),
            )
        return self.parameter_data

    def parameter(self, params: dict, logger: PolicyEngineLogger) -> dict:
        """Get a specific parameter."""
        return self.parameter_data[params["q"]]

    @cached_endpoint
    def budgetary_impact(
        self, params: dict, logger: PolicyEngineLogger
    ) -> dict:
        """Get the budgetary impact of a reform."""
        baseline, reformed = self.create_microsimulations(params)
        baseline_net_income = baseline.calc(
            self.results_config.household_net_income_variable
        ).sum()
        reformed_net_income = reformed.calc(
            self.results_config.household_net_income_variable
        ).sum()
        difference = reformed_net_income - baseline_net_income
        return {
            "budgetary_impact": difference,
        }

    def calculate(
        self,
        params: dict,
        logger: PolicyEngineLogger,
    ) -> dict:
        """Calculate variables for a given household and policy reform."""
        if len(params) == 1:
            # Cache the tax-benefit system for no-reform simulations
            system = self.tax_benefit_system
        else:
            reform = self.create_reform(params)
            system = apply_reform(
                reform.reform, self.tax_benefit_system_type()
            )
        simulation = SimulationBuilder().build_from_entities(
            system, params["household"]
        )

        requested_computations = dpath.util.search(
            params["household"],
            "*/*/*/*",
            afilter=lambda t: t is None,
            yielded=True,
        )
        computation_results = {}

        for computation in requested_computations:
            path = computation[0]
            entity_plural, entity_id, variable_name, period = path.split("/")
            variable = system.get_variable(variable_name)
            result = simulation.calculate(variable_name, period)
            population = simulation.get_population(entity_plural)
            entity_index = population.get_index(entity_id)

            if variable.value_type == Enum:
                entity_result = result.decode()[entity_index].name
            elif variable.value_type == float:
                entity_result = float(str(result[entity_index]))
            elif variable.value_type == str:
                entity_result = str(result[entity_index])
            else:
                entity_result = result.tolist()[entity_index]

            # Bug fix, unclear of the root cause

            if isinstance(entity_result, list) and len(entity_result) > 2_000:
                entity_result = {period: entity_result[-1]}

            dpath.util.new(computation_results, path, entity_result)

        dpath.util.merge(params["household"], computation_results)

        return params["household"]

    def population_reform_runtime(
        self, params: dict, logger: PolicyEngineLogger
    ) -> dict:
        """Get the average runtime of a population reform."""
        return {
            "reform_only": np.average(
                self.population_reform_recent_calls["reform_only"]
            ),
            "reform_and_baseline": np.average(
                self.population_reform_recent_calls["reform_and_baseline"]
            ),
        }

    @cached_endpoint
    def population_reform(
        self, params: dict, logger: PolicyEngineLogger
    ) -> dict:
        """Compute the population-level impact of a reform."""
        start_time = time()
        edits_baseline = any(["baseline_" in param for param in params])
        baseline, reformed = self.create_microsimulations(params)
        rel_income_decile_chart, avg_income_decile_chart = decile_chart(
            baseline, reformed, self.results_config
        )
        rel_wealth_decile_chart, avg_wealth_decile_chart = decile_chart(
            baseline,
            reformed,
            self.results_config,
            decile_type="wealth",
        )
        result = dict(
            **headline_metrics(baseline, reformed, self.results_config),
            rel_income_decile_chart=rel_income_decile_chart,
            avg_income_decile_chart=avg_income_decile_chart,
            rel_wealth_decile_chart=rel_wealth_decile_chart,
            avg_wealth_decile_chart=avg_wealth_decile_chart,
            poverty_chart=poverty_chart(
                baseline, reformed, False, self.results_config
            ),
            deep_poverty_chart=poverty_chart(
                baseline, reformed, True, self.results_config
            ),
            waterfall_chart=waterfall_chart(
                baseline, reformed, self.results_config
            ),
            intra_income_decile_chart=intra_decile_chart(
                baseline, reformed, self.results_config
            ),
            intra_wealth_decile_chart=intra_decile_chart(
                baseline,
                reformed,
                self.results_config,
                decile_type="wealth",
            ),
            inequality_chart=inequality_chart(
                baseline,
                reformed,
                self.results_config,
            ),
        )
        if len(self.population_reform_recent_calls["reform_only"]) > 10:
            self.population_reform_recent_calls["reform_only"].pop(0)
        if (
            len(self.population_reform_recent_calls["reform_and_baseline"])
            > 10
        ):
            self.population_reform_recent_calls["reform_and_baseline"].pop(0)
        if edits_baseline:
            self.population_reform_recent_calls["reform_and_baseline"].append(
                time() - start_time
            )
        else:
            self.population_reform_recent_calls["reform_only"].append(
                time() - start_time
            )
        return result
