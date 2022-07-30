from pathlib import Path
from tkinter import Variable
from typing import Type
from openfisca_core.parameters.helpers import load_parameter_file
from openfisca_core.parameters import ParameterNode
from openfisca_core.reforms.reform import Reform
from openfisca_core.taxbenefitsystems import TaxBenefitSystem
from openfisca_core.tracers.tracing_parameter_node_at_instant import (
    ParameterNode,
)


def add_parameter_file(path: str) -> Reform:
    """Generates a reform adding a parameter file to the tree.

    Args:
        path (str): The path to the parameter YAML file.

    Returns:
        Reform: The Reform adding the parameters.
    """

    def modify_parameters(parameters: ParameterNode):
        file_path = Path(path)
        reform_parameters_subtree = load_parameter_file(file_path)
        parameters.add_child("reforms", reform_parameters_subtree.reforms)
        return parameters

    class reform(Reform):
        def apply(self):
            self.modify_parameters(modify_parameters)

    return reform


def structural(variable: Type[Variable]) -> Reform:
    """Generates a structural reform.

    Args:
        variable (Type[Variable]): The class definition of a variable to replace.

    Returns:
        Reform: The reform object.
    """
    return type(
        variable.__name__,
        (Reform,),
        dict(apply=lambda self: self.update_variable(variable)),
    )


def reinstate_variable(system, variable):
    clone = system.variables[variable].clone()
    clone.is_neutralized = False
    system.variables[variable] = clone


def abolish(variable: str, neutralize: bool = True) -> Reform:
    if neutralize:
        return type(
            f"abolish_{variable}",
            (Reform,),
            dict(apply=lambda self: self.neutralize_variable(variable)),
        )
    else:
        return type(
            f"reinstate_{variable}",
            (Reform,),
            dict(apply=lambda self: reinstate_variable(self, variable)),
        )


def parametric(
    parameter: str, value: float, period: str = "year:2015:20"
) -> Reform:
    """Generates a parametric reform.

    Args:
        parameter (str): The name of the parameter, e.g. tax.income_tax.rate.
        value (float): The value to set as the parameter value.
        period (str): The time period to set it for. Defaults to a ten-year period from 2015 to 2025.

    Returns:
        Reform: The reform object.
    """

    def modifier_fn(parameters: ParameterNode):
        node = parameters
        for name in parameter.split("."):
            try:
                if "[" not in name:
                    node = node.children[name]
                else:
                    try:
                        name, index = name.split("[")
                        index = int(index[:-1])
                        node = node.children[name].brackets[index]
                    except:
                        raise ValueError(
                            "Invalid bracket syntax (should be e.g. tax.brackets[3].rate"
                        )
            except:
                raise ValueError(
                    f"Could not find the parameter (failed at {name})."
                )
        node.update(period=period, value=value)
        return parameters

    return type(
        parameter,
        (Reform,),
        dict(apply=lambda self: self.modify_parameters(modifier_fn)),
    )


def apply_reform(reform: tuple, system: TaxBenefitSystem) -> TaxBenefitSystem:
    """Applies a reform to a system.

    Args:
        reform (tuple): The reform to apply.
        system (TaxBenefitSystem): The system to apply it to.

    Returns:
        TaxBenefitSystem: The system with the reform applied.
    """
    if not hasattr(system, "modify_parameters"):

        def modify_parameters(self, modifier):
            self.parameters = modifier(self.parameters)

        system.modify_parameters = modify_parameters.__get__(system)
    if isinstance(reform, tuple):
        for subreform in reform:
            system = apply_reform(subreform, system)
    else:
        reform.apply(system)
    return system
