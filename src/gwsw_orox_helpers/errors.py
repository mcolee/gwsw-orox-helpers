"""Uitzonderingen van gwsw-orox-helpers."""


class OroxError(Exception):
    """Basisfout van de leeslaag; afnemers vangen deze."""


class DatasetError(OroxError):
    """De OroX-dataset ontbreekt, is onleesbaar of bevat geen toetsbare objecten."""
