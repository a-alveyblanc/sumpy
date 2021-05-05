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

import numpy as np
import sys

import pyopencl as cl
from pyopencl.tools import (  # noqa
        pytest_generate_tests_for_pyopencl as pytest_generate_tests)

import logging
logger = logging.getLogger(__name__)
from sumpy.expansion.local import (
        LineTaylorLocalExpansion, VolumeTaylorLocalExpansion)
import pytest


@pytest.mark.parametrize("expn_class", [
            LineTaylorLocalExpansion,
            VolumeTaylorLocalExpansion,
            ])
def test_direct_qbx_vs_eigval(ctx_factory, expn_class):
    """This evaluates a single layer potential on a circle using a known
    eigenvalue/eigenvector combination.
    """

    logging.basicConfig(level=logging.INFO)

    ctx = ctx_factory()
    queue = cl.CommandQueue(ctx)

    from sumpy.kernel import LaplaceKernel
    lknl = LaplaceKernel(2)

    order = 12

    from sumpy.qbx import LayerPotential

    lpot = LayerPotential(ctx, expansion=expn_class(lknl, order),
            target_kernels=(lknl,), source_kernels=(lknl,))

    mode_nr = 25

    from pytools.convergence import EOCRecorder

    eocrec = EOCRecorder()

    for n in [200, 300, 400]:
        t = np.linspace(0, 2 * np.pi, n, endpoint=False)
        unit_circle = np.exp(1j * t)
        unit_circle = np.array([unit_circle.real, unit_circle.imag])

        sigma = np.cos(mode_nr * t)
        eigval = 1/(2*mode_nr)

        result_ref = eigval * sigma

        h = 2 * np.pi / n

        targets = unit_circle
        sources = unit_circle

        radius = 7 * h
        centers = unit_circle * (1 - radius)

        expansion_radii = np.ones(n) * radius

        strengths = (sigma * h,)
        evt, (result_qbx,) = lpot(queue, targets, sources, centers, strengths,
                expansion_radii=expansion_radii)

        eocrec.add_data_point(h, np.max(np.abs(result_ref - result_qbx)))

    print(eocrec)

    slack = 1.5
    assert eocrec.order_estimate() > order - slack


@pytest.mark.parametrize("expn_class", [
            LineTaylorLocalExpansion,
            VolumeTaylorLocalExpansion,
            ])
def test_direct_qbx_vs_eigval_with_tgt_deriv(ctx_factory, expn_class):
    """This evaluates a single layer potential on a circle using a known
    eigenvalue/eigenvector combination.
    """

    logging.basicConfig(level=logging.INFO)

    ctx = ctx_factory()
    queue = cl.CommandQueue(ctx)

    from sumpy.kernel import LaplaceKernel, AxisTargetDerivative
    lknl = LaplaceKernel(2)

    order = 8

    from sumpy.qbx import LayerPotential

    lpot_dx = LayerPotential(ctx, expansion=expn_class(lknl, order),
            target_kernels=(AxisTargetDerivative(0, lknl),), source_kernels=(lknl,))
    lpot_dy = LayerPotential(ctx, expansion=expn_class(lknl, order),
            target_kernels=(AxisTargetDerivative(1, lknl),), source_kernels=(lknl,))

    mode_nr = 15

    from pytools.convergence import EOCRecorder

    eocrec = EOCRecorder()

    for n in [200, 300, 400]:
        t = np.linspace(0, 2 * np.pi, n, endpoint=False)
        unit_circle = np.exp(1j * t)
        unit_circle = np.array([unit_circle.real, unit_circle.imag])

        sigma = np.cos(mode_nr * t)
        #eigval = 1/(2*mode_nr)
        eigval = 0.5

        result_ref = eigval * sigma

        h = 2 * np.pi / n

        targets = unit_circle
        sources = unit_circle

        radius = 7 * h
        centers = unit_circle * (1 - radius)

        expansion_radii = np.ones(n) * radius

        strengths = (sigma * h,)

        evt, (result_qbx_dx,) = lpot_dx(queue, targets, sources, centers, strengths,
                expansion_radii=expansion_radii)
        evt, (result_qbx_dy,) = lpot_dy(queue, targets, sources, centers, strengths,
                expansion_radii=expansion_radii)

        normals = unit_circle
        result_qbx = normals[0] * result_qbx_dx + normals[1] * result_qbx_dy

        eocrec.add_data_point(h, np.max(np.abs(result_ref - result_qbx)))

    if expn_class is not LineTaylorLocalExpansion:
        print(eocrec)

        slack = 1.5
        assert eocrec.order_estimate() > order - slack


if __name__ == "__main__":
    if len(sys.argv) > 1:
        exec(sys.argv[1])
    else:
        from pytest import main
        main([__file__])

# vim: fdm=marker
