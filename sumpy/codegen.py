from __future__ import division

import numpy as np
import pyopencl as cl
import pyopencl.tools

import re

from pymbolic.mapper import IdentityMapper, WalkMapper
import pymbolic.primitives as prim

from pytools import memoize_method


# {{{ bessel handling

BESSEL_PREAMBLE = (
"""//CL//
#include <pyopencl-bessel-j.cl>
#include <pyopencl-bessel-y.cl>

typedef struct hank1_01_result_str
{
    cdouble_t order0, order1;
} hank1_01_result;

hank1_01_result hank1_01(cdouble_t z)
{
    hank1_01_result result;
    result.order0 = cdouble_new(bessel_j0(z.x), bessel_y0(z.x));
    result.order1 = cdouble_new(bessel_j1(z.x), bessel_y1(z.x));
    return result;
}
""")

hank1_01_result_dtype = cl.tools.get_or_register_dtype("hank1_01_result",
        np.dtype([
            ("order0", np.complex128),
            ("order1", np.complex128),
            ]),
        )

def bessel_mangler(identifier, arg_dtypes):
    if identifier == "hank1_01":
        return np.dtype(hank1_01_result_dtype), identifier, (np.dtype(np.complex128),)
    if identifier == "bessel_jv":
        return np.dtype(np.float64), identifier

    return None



class BesselGetter(object):
    def __init__(self, bessel_j_arg_to_top_order):
        self.bessel_j_arg_to_top_order = bessel_j_arg_to_top_order

    @memoize_method
    def hank1_01(self, arg):
        return prim.Variable("hank1_01")(arg)

    @memoize_method
    def bessel_j_impl(self, order, arg):
        return prim.Variable("bessel_jv")(order, arg)

    @memoize_method
    def hankel_1(self, order, arg):
        if order == 0:
            return prim.Lookup(
                    prim.CommonSubexpression(self.hank1_01(arg), "hank1_01_result"),
                    "order0")
        elif order == 1:
            return prim.Lookup(
                    prim.CommonSubexpression(self.hank1_01(arg), "hank1_01_result"),
                    "order1")
        elif order < 0:
            # AS (9.1.6)
            nu = -order
            return prim.wrap_in_cse(
                    (-1)**nu * self.hankel_1(nu, arg),
                    "hank1_neg%d" % nu)
        elif order > 1:
            # AS (9.1.27)
            nu = order-1
            return prim.CommonSubexpression(
                    2*nu/arg*self.hankel_1(nu, arg)
                    - self.hankel_1(nu-1, arg),
                    "hank1_%d" % order)
        else:
            assert False

    @memoize_method
    def bessel_j(self, order, arg):
        top_order = self.bessel_j_arg_to_top_order[arg]

        if order == top_order:
            return prim.CommonSubexpression(
                    self.bessel_j_impl(order, arg),
                    "bessel_j_%d" % order)
        elif order == top_order-1:
            return prim.CommonSubexpression(
                    self.bessel_j_impl(order, arg),
                    "bessel_j_%d" % order)
        elif order < 0:
            return (-1)**order*self.bessel_j(-order, arg)
        else:
            assert abs(order) < top_order

            # AS (9.1.27)
            nu = order+1
            return prim.CommonSubexpression(
                    2*nu/arg*self.bessel_j(nu, arg)
                    - self.bessel_j(nu+1, arg),
                    "bessel_j_%d" % order)





class BesselTopOrderGatherer(WalkMapper):
    """This mapper walks the expression tree to find the highest-order
    Bessel J being used, so that all other Js can be computed by the
    (stable) downward recurrence.
    """
    def __init__(self):
        self.bessel_j_arg_to_top_order = {}

    def map_call(self, expr):
        if isinstance(expr.function, prim.Variable) and expr.function.name == "bessel_j":
            order, arg = expr.parameters
            self.rec(arg)
            assert isinstance(order, int)
            self.bessel_j_arg_to_top_order[arg] = max(
                    self.bessel_j_arg_to_top_order.get(arg, 0),
                    abs(order))
        else:
            return WalkMapper.map_call(self, expr)




class BesselDerivativeReplacer(IdentityMapper):
    def map_substitution(self, expr):
        assert isinstance(expr.child, prim.Derivative)
        call = expr.child.child

        if (isinstance(call.function, prim.Variable)
                and call.function.name in ["hankel_1", "bessel_j"]):
            function = call.function
            order, _ = call.parameters
            arg, = expr.values

            n_derivs = len(expr.child.variables)
            import sympy as sp

            # AS (9.1.31)
            if order >= 0:
                order_str = str(order)
            else:
                order_str = "m"+str(-order)
            k = n_derivs
            return prim.CommonSubexpression(
                    2**(-k)*sum(
                        (-1)**idx*int(sp.binomial(k, idx)) * function(i, arg)
                        for idx, i in enumerate(range(order-k, order+k+1, 2))),
                    "d%d_%s_%s" % (n_derivs, function.name, order_str))
        else:
            return IdentityMapper.map_substitution(self, expr)




class BesselSubstitutor(IdentityMapper):
    def __init__(self, bessel_getter):
        self.bessel_getter = bessel_getter

    def map_call(self, expr):
        if isinstance(expr.function, prim.Variable):
            name = expr.function.name
            if name in ["hankel_1", "bessel_j"]:
                order, arg = expr.parameters
                return getattr(self.bessel_getter, name)(order, self.rec(arg))

        return IdentityMapper.map_call(self, expr)

# }}}




class PowerRewriter(IdentityMapper):
    def map_power(self, expr):
        exp = expr.exponent
        if isinstance(exp, int):
            new_base = prim.wrap_in_cse(expr.base)

            if exp > 1 and exp % 2 == 0:
                square = prim.wrap_in_cse(new_base*new_base)
                return self.rec(prim.wrap_in_cse(square**(exp//2)))
            if exp > 1 and exp % 2 == 1:
                square = prim.wrap_in_cse(new_base*new_base)
                return self.rec(prim.wrap_in_cse(square**((exp-1)//2))*new_base)
            elif exp == 1:
                return new_base
            elif exp < 0:
                return self.rec((1/new_base)**(-exp))

        if (isinstance(expr.exponent, prim.Quotient)
                and isinstance(expr.exponent.numerator, int)
                and isinstance(expr.exponent.denominator, int)):

            p, q = expr.exponent.numerator, expr.exponent.denominator
            if q < 0:
                q *= -1
                p *= -1

            if q == 1:
                return self.rec(new_base**p)

            if q == 2:
                assert p != 0

                if p > 0:
                    orig_base = prim.wrap_in_cse(expr.base)
                    new_base = prim.wrap_in_cse(prim.Variable("sqrt")(orig_base))
                else:
                    new_base = prim.wrap_in_cse(prim.Variable("rsqrt")(expr.base))
                    p *= -1

                return self.rec(new_base**p)

        return IdentityMapper.map_power(self, expr)





class FractionKiller(IdentityMapper):
    def map_quotient(self, expr):
        num = expr.numerator
        denom = expr.denominator

        if isinstance(num, int) and isinstance(denom, int):
            if num % denom == 0:
                return num // denom
            return int(expr.numerator) / int(expr.denominator)

        return IdentityMapper.map_quotient(self, expr)




INDEXED_VAR_RE = re.compile("^([a-zA-Z_]+)([0-9]+)$")

class VectorComponentRewriter(IdentityMapper):
    def __init__(self, name_whitelist=set()):
        self.name_whitelist = name_whitelist

    def map_variable(self, expr):
        match_obj = INDEXED_VAR_RE.match(expr.name)
        if match_obj is not None:
            name = match_obj.group(1)
            subscript = int(match_obj.group(2))
            if name in self.name_whitelist:
                return prim.Variable(name)[subscript]
            else:
                return IdentityMapper.map_variable(self, expr)
        else:
            return IdentityMapper.map_variable(self, expr)




class SumSignGrouper(IdentityMapper):
    def map_sum(self, expr):
        first_group = []
        second_group = []

        for child in expr.children:
            tchild = child
            if isinstance(tchild, prim.CommonSubexpression):
                tchild = tchild.child

            if isinstance(tchild, prim.Product):
                neg_int_count = 0
                for subchild in tchild.children:
                    if isinstance(subchild, int) and subchild < 0:
                        neg_int_count += 1

                if neg_int_count % 2 == 1:
                    second_group.append(child)
                else:
                    first_group.append(child)
            else:
                first_group.append(child)

        return prim.Sum(tuple(first_group+second_group))






class MathConstantRewriter(IdentityMapper):
    def map_variable(self, expr):
        if expr.name == "pi":
            return prim.Variable("M_PI")
        else:
            return IdentityMapper.map_variable(self, expr)




class ComplexConstantSizer(IdentityMapper):
    def __init__(self, dtype):
        self.dtype = dtype

    def map_constant(self, expr):
        if isinstance(expr, (complex, np.complexfloating)):
            assert self.dtype.kind == "c"
            return self.dtype.type(expr)
        else:
            return expr





def to_loopy_insns(assignments, vector_names=set(), pymbolic_expr_maps=[],
        complex_dtype=None):
    # convert from sympy
    from pymbolic.sympy_interface import SympyToPymbolicMapper
    sympy_conv = SympyToPymbolicMapper()
    assignments = [(name, sympy_conv(expr)) for name, expr in assignments]

    bdr = BesselDerivativeReplacer()
    assignments = [(name, bdr(expr)) for name, expr in assignments]

    btog = BesselTopOrderGatherer()
    for name, expr in assignments:
        btog(expr)

    # do the rest of the conversion
    bessel_sub = BesselSubstitutor(BesselGetter(btog.bessel_j_arg_to_top_order))
    vcr = VectorComponentRewriter(vector_names)
    pwr = PowerRewriter()
    ssg = SumSignGrouper()
    fck = FractionKiller()
    if complex_dtype is not None:
        ccs = ComplexConstantSizer(np.dtype(complex_dtype))
    else:
        ccs = None

    def convert_expr(expr):
        expr = bdr(expr)
        expr = bessel_sub(expr)
        expr = vcr(expr)
        expr = pwr(expr)
        expr = fck(expr)
        expr = ssg(expr)
        if ccs is not None:
            expr = ccs(expr)
        for m in pymbolic_expr_maps:
            expr = m(expr)
        return expr

    import loopy as lp
    return [
            lp.Instruction(id=None,
                assignee=name, expression=convert_expr(expr),
                temp_var_type=lp.infer_type)
            for name, expr in assignments]
