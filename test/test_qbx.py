__copyright__ = "Copyright (C) 2017 Matt Wala"

__license__ = """
Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.
"""

import pytest
import sys

import numpy as np

from arraycontext import pytest_generate_tests_for_array_contexts
from sumpy.array_context import (                                 # noqa: F401
        PytestPyOpenCLArrayContextFactory, _acf)

from sumpy.expansion.local import (
        LineTaylorLocalExpansion,
        VolumeTaylorLocalExpansion)

import logging
logger = logging.getLogger(__name__)

pytest_generate_tests = pytest_generate_tests_for_array_contexts([
    PytestPyOpenCLArrayContextFactory,
    ])


# {{{ test_direct_qbx_vs_eigval

@pytest.mark.parametrize("expn_class", [
            LineTaylorLocalExpansion,
            VolumeTaylorLocalExpansion,
            ])
def test_direct_qbx_vs_eigval(actx_factory, expn_class, visualize=False):
    """This evaluates a single layer potential on a circle using a known
    eigenvalue/eigenvector combination.
    """
    if visualize:
        logging.basicConfig(level=logging.INFO)

    actx = actx_factory()

    from sumpy.kernel import LaplaceKernel
    lknl = LaplaceKernel(2)

    order = 12

    from sumpy.qbx import LayerPotential

    lpot = LayerPotential(
            expansion=expn_class(lknl, order),
            target_kernels=(lknl,),
            source_kernels=(lknl,))

    mode_nr = 25

    from pytools.convergence import EOCRecorder

    eocrec = EOCRecorder()

    for n in [200, 300, 400]:
        t = actx.from_numpy(np.linspace(0, 2 * np.pi, n, endpoint=False))
        unit_circle = actx.np.stack([actx.np.cos(t), actx.np.sin(t)])

        sigma = actx.np.cos(mode_nr * t)
        eigval = 1/(2*mode_nr)

        result_ref = eigval * sigma

        h = 2 * np.pi / n

        targets = unit_circle
        sources = unit_circle

        radius = 7 * h
        centers = unit_circle * (1 - radius)
        expansion_radii = actx.from_numpy(np.full(n, radius))

        strengths = (sigma * h,)
        result_qbx = lpot(
                actx,
                targets, sources, centers, strengths,
                expansion_radii=expansion_radii)["result_0"]

        error = actx.to_numpy(
            actx.np.linalg.norm(result_ref - result_qbx, np.inf))
        eocrec.add_data_point(h, error)

    logger.info("eoc:\n%s", eocrec)

    slack = 1.5
    assert eocrec.order_estimate() > order - slack

# }}}


# {{{ test_direct_qbx_vs_eigval_with_tgt_deriv

@pytest.mark.parametrize("expn_class", [
            LineTaylorLocalExpansion,
            VolumeTaylorLocalExpansion,
            ])
def test_direct_qbx_vs_eigval_with_tgt_deriv(
        actx_factory, expn_class, visualize=False):
    """This evaluates a single layer potential on a circle using a known
    eigenvalue/eigenvector combination.
    """
    if visualize:
        logging.basicConfig(level=logging.INFO)

    actx = actx_factory()

    from sumpy.kernel import LaplaceKernel, AxisTargetDerivative
    lknl = LaplaceKernel(2)

    order = 8

    from sumpy.qbx import LayerPotential

    lpot_dx = LayerPotential(
        expansion=expn_class(lknl, order),
        target_kernels=(AxisTargetDerivative(0, lknl),),
        source_kernels=(lknl,))
    lpot_dy = LayerPotential(
        expansion=expn_class(lknl, order),
        target_kernels=(AxisTargetDerivative(1, lknl),),
        source_kernels=(lknl,))

    mode_nr = 15

    from pytools.convergence import EOCRecorder

    eocrec = EOCRecorder()

    for n in [200, 300, 400]:
        t = actx.from_numpy(np.linspace(0, 2 * np.pi, n, endpoint=False))
        unit_circle = actx.np.stack([actx.np.cos(t), actx.np.sin(t)])

        sigma = actx.np.cos(mode_nr * t)
        #eigval = 1/(2*mode_nr)
        eigval = 0.5

        result_ref = eigval * sigma

        h = 2 * np.pi / n

        targets = unit_circle
        sources = unit_circle

        radius = 7 * h
        centers = unit_circle * (1 - radius)

        expansion_radii = actx.from_numpy(np.full(n, radius))

        strengths = (sigma * h,)

        result_qbx_dx = lpot_dx(actx,
                targets, sources, centers, strengths,
                expansion_radii=expansion_radii)["result_0"]
        result_qbx_dy = lpot_dy(actx,
                targets, sources, centers, strengths,
                expansion_radii=expansion_radii)["result_0"]

        normals = unit_circle
        result_qbx = normals[0] * result_qbx_dx + normals[1] * result_qbx_dy

        error = actx.to_numpy(
            actx.np.linalg.norm(result_ref - result_qbx, np.inf))
        eocrec.add_data_point(h, error)

    if expn_class is not LineTaylorLocalExpansion:
        logger.info("eoc:\n%s", eocrec)

        slack = 1.5
        assert eocrec.order_estimate() > order - slack

# }}}


# You can test individual routines by typing
# $ python test_qbx.py 'test_direct_qbx_vs_eigval(_acf, LineTaylorLocalExpansion)'

if __name__ == "__main__":
    if len(sys.argv) > 1:
        exec(sys.argv[1])
    else:
        pytest.main([__file__])

# vim: fdm=marker
