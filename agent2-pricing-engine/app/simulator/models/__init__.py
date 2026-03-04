"""Simulator model packages — import all sub-packages to trigger registration."""

from app.simulator.models import equity  # noqa: F401
from app.simulator.models import fx  # noqa: F401
from app.simulator.models import rates  # noqa: F401
from app.simulator.models import credit  # noqa: F401
from app.simulator.models import commodity  # noqa: F401
from app.simulator.models import income  # noqa: F401
from app.simulator.models import greeks  # noqa: F401
from app.simulator.models import volsurface  # noqa: F401
