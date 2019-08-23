import z3
from utils import resolve_type
import math
import numpy as np
from itertools import product
import warnings
import copy
import bisect

magic = "Max~~"


class Solver:
    solver = z3.Solver()
    index = {}
    variable_by_name = {}

    @staticmethod
    def add_variable(name, dtype):
        if name not in Solver.index:
            Solver.index[name] = 0
        variable_name = name + "_" + str(Solver.index[name])
        Solver.index[name] += 1
        if dtype in [3]:
            real_name = variable_name + "_Int"
            Solver.variable_by_name[real_name] = z3.Int(real_name)
        elif dtype in [1]:
            real_name = variable_name + "_Real"
            Solver.variable_by_name[real_name] = z3.Real(real_name)
        elif dtype in [10]:
            real_name = variable_name + "_Bool"
            Solver.variable_by_name[real_name] = z3.Bool(real_name)
        else:
            raise NotImplementedError("Cannot Recognize: ", dtype)
        return Solver.variable_by_name[real_name]

    # @staticmethod
    # def new_variable(real_name, dtype):
    #     if dtype in [3]:
    #         Solver.variable_by_name[real_name] = z3.Int(real_name)
    #     elif dtype in [1]:
    #         Solver.variable_by_name[real_name] = z3.Real(real_name)
    #     elif dtype in [10]:
    #         Solver.variable_by_name[real_name] = z3.Bool(real_name)
    #     else:
    #         Solver.variable_by_name[real_name] = z3.Real(real_name)
    #         warnings.warn("Cannot Recognize: " + str(dtype), RuntimeWarning)
    #     return Solver.variable_by_name[real_name]
    #
    # @staticmethod
    # def add_variable_list(variables: list):
    #     for (x, y) in variables:
    #         name = x + " " + str(y)
    #         Solver.new_variable(name, Array.name_to_dtype[x])
    #
    # @staticmethod
    # def to_variable(x: tuple):
    #     return Solver.variable_by_name[x[0] + " " + str(x[1])]

    @staticmethod
    def max(x, ys_):
        ys1 = [y for y in list(map(resolve_type, ys_)) if str(y) != 'inf']
        ys = [y for y in ys1 if str(y) != '-inf']
        if len(ys1) != len(ys_):
            z3.And([x >= y for y in ys])

        try:
            return x == max(ys)
        except:
            pass
        if len(ys) == 1:
            return x == ys[0]
        if len(ys) == 2:
            return x == z3.If(ys[0] > ys[1], ys[0], ys[1])
        return z3.And(z3.Or([x == y for y in ys]), z3.And([x >= y for y in ys]))

    @staticmethod
    def min(x, ys_):
        ys1 = [y for y in list(map(resolve_type, ys_)) if str(y) != '-inf']
        ys = [y for y in ys1 if str(y) != 'inf']
        if len(ys1) != len(ys_):
            z3.And([x <= y for y in ys])

        try:
            return x == min(ys)
        except:
            pass
        if len(ys) == 1:
            return x == ys[0]
        if len(ys) == 2:
            return x == z3.If(ys[0] < ys[1], ys[0], ys[1])
        return z3.And(z3.Or([x == y for y in ys]), z3.And([x <= y for y in ys]))

    @staticmethod
    def in_interval(x, interval):
        if isinstance(interval, tuple):
            if interval[0] > 0 or interval[1] > 0:
                # (a, b]
                if math.isinf(interval[1]):
                    return z3.And(interval[0] < x)
                else:
                    return z3.And(interval[0] <= x, x <= interval[1])
            else:
                # [a, b)
                if math.isinf(interval[0]):
                    return z3.And(x < interval[1])
                else:
                    return z3.And(interval[0] <= x, x <= interval[1])
        else:
            return x == interval


class Range:
    def __init__(self, *args, **kwargs):
        """Two ways of construction:
                left, right
                name, dtype
            One optional parameter for range_const

            The int and float tensor representation --> interval
            The bool tensor representation -->  [True, False] for all False,
                                                [False, True] for all True,
                                                [True, True] for both True and False
        """
        if "const_type" in kwargs:
            self.const_type = kwargs["const_type"]
        else:
            self.const_type = None
        if "name" in kwargs and "dtype" in kwargs:
            name = kwargs["name"]
            dtype = kwargs["dtype"]
            self.left = Solver.add_variable(name + "L", dtype)
            self.right = Solver.add_variable(name + "R", dtype)
        elif "left" in kwargs and "right" in kwargs:
            self.left = resolve_type(kwargs["left"])
            self.right = resolve_type(kwargs["right"])
        else:
            raise NotImplementedError(args, kwargs, " setting not implemented")

    def __str__(self):
        return "[%s, %s]\n[%s, %s]" % (self.left, self.right, str(type(self.left)), str(type(self.right)))

    def __repr__(self):
        return "[%s, %s]\n[%s, %s]" % (self.left, self.right, str(type(self.left)), str(type(self.right)))

    def __mul__(self, other):
        return Range(left=None if self.left is None else self.left * other,
                     right=None if self.right is None else self.right * other,
                     const_type=self.const_type)

    def __add__(self, other):
        return Range(left=None if self.left is None else self.left + other,
                     right=None if self.right is None else self.right + other,
                     const_type=self.const_type)


class Linear:
    def __init__(self, e):
        self.value = [(e, 1)]
        self.map_to_index = [list(range(len(e[1])))]

    def __str__(self):
        return "%s\n%s" % (str(self.value), str(self.map_to_index))

    def __repr__(self):
        return "%s\n%s" % (str(self.value), str(self.map_to_index))

    def __add__(self, other):
        ret = copy.deepcopy(self)
        ret.value += other.value
        ret.map_to_index += other.map_to_index
        return ret

    def __sub__(self, other):
        ret = copy.deepcopy(self)
        for i in range(len(other.value)):
            ret.value.append((other.value[i][0], -other.value[i][1]))
        ret.map_to_index += other.map_to_index
        return ret

    def choose(self, start_ind):
        # len(start_ind) = len(x[1]) = len(map)
        ret = copy.deepcopy(self)
        ret.value = []
        ret.map_to_index = []
        for (ii, (x, factor)) in enumerate(self.value):
            name, position = x
            new_tp = list(position)  # if not mapped, then remain
            map = self.map_to_index[ii]
            for t in range(len(start_ind)):
                if map[t] is not None:
                    i = map[t]
                    if start_ind[t] is not None:
                        new_tp[i] = (new_tp[i][0] + start_ind[t][0], new_tp[i][0] + start_ind[t][1])

            ret.value.append(((name, position), factor))
            ret.map_to_index.append(map)

        return ret

    def transpose(self, perm):
        # len(perm) = len(x[1]) = len(map)
        ret = copy.deepcopy(self)
        for i in range(len(self.value)):
            map = self.map_to_index[i]
            new_map = [None] * len(map)
            for t in range(len(perm)):
                new_map[t] = map[perm[t]]
            ret.map_to_index[i] = new_map

        return ret

    def add_pack_ind(self, pack_ind):
        ret = copy.deepcopy(self)
        for i in range(len(self.value)):
            map = self.map_to_index[i]
            new_map = map[:pack_ind] + [None] + map[pack_ind:]
            ret.map_to_index[i] = new_map

        return ret

    def remove_unpack_axis(self, axis):
        ret = copy.deepcopy(self)
        for i in range(len(self.value)):
            map = self.map_to_index[i]
            new_map = map[:axis] + map[axis:]
            ret.map_to_index[i] = new_map

        return ret

    def neg(self):
        for i in range(len(self.value)):
            x, factor = self.value[i]
            self.value[i] = (x, -factor)

    # def relu(self):
    #     assert len(self.value) <= 1
    #     ret = Linear(("dumy", (0, 1)))
    #     ret.value = {}
    #     ret.map_to_index = {}
    #     for x in self.value:
    #         name, position = x
    #         if name[:5] != magic:
    #             ret.value[(magic + name, position)] = self.value[x]
    #             ret.map_to_index[(magic + name, position)] = self.map_to_index[x]
    #     return ret


class Array:

    def __init__(self, name, size):
        self.index_slices = []
        self.block_to_symbol = {}
        self.name = name
        try:
            len(size)
        except:
            self.index_slices = None
            return

        # try:
        #     if len(size) == 1:
        #         int(size[0])
        # except:
        #     self.index_slices = [None]
        #     self.block_to_symbol = {(None,): symbol}
        #     return
        #
        # if len(size) == 0 or (len(size) == 1 and int(size[0]) == 0):
        #     self.index_slices = [[1]]
        #     self.block_to_symbol = {(1,): symbol}
        # else:
        for i in range(len(size)):
            try:
                self.index_slices.append([int(size[i])])
            except:
                self.index_slices.append([None])
        self.block_to_symbol = {
            tuple([x[0] for x in self.index_slices]): Linear((name, tuple([(0, x[0]) for x in self.index_slices])))}

    @staticmethod
    def join_index_slices(a, b):
        ret = []
        for i in range(len(a)):
            if a[i][0] is None and b[i][0] is None:
                ret.append([None])
            else:
                assert a[i][0] is not None and b[i][0] is not None
                c = np.unique(a[i] + b[i])
                ret.append(list(c))

        return ret

    def get_corresponding_keys(self, index_slices):
        ret = []
        for indexes in product(*index_slices):
            key = ()
            start_ind = []
            for i in range(len(indexes)):
                if indexes[i] is not None:
                    t = bisect.bisect_left(index_slices[i], indexes[i])
                    start_ind.append([0 if t == 0 else index_slices[i][t - 1], indexes[i]])
                    iargs = bisect.bisect_left(self.index_slices[i], indexes[i])
                    if iargs > 0:
                        start_ind[-1][0] -= self.index_slices[i][iargs - 1]
                        start_ind[-1][1] -= self.index_slices[i][iargs - 1]

                    key += (self.index_slices[i][iargs],)
                else:
                    key += (None,)
                    start_ind.append(None)

            ret.append(self.block_to_symbol[key].choose(start_ind))

        return ret

    def flush(self, name):
        self.block_to_symbol = {}
        for indexes in product(*self.index_slices):
            new_tp = ()
            for (i, x) in enumerate(indexes):
                if x is None:
                    new_tp += ((0, None),)
                else:
                    t = bisect.bisect_left(self.index_slices[i], x)
                    new_tp += ((0 if t == 0 else self.index_slices[i][t - 1], x),)
            self.block_to_symbol[tuple(indexes)] = Linear((name, new_tp))

    # def get_possible_values(self):
    #     ret = []
    #     for ix in self.block_to_symbol:
    #         flag = True
    #         x = self.block_to_symbol[ix]
    #         for y in ret:
    #             if y.equals(x):
    #                 flag = False
    #                 break
    #
    #         if flag:
    #             ret.append(x)
    #
    #     return [str_2_linear_expression(str(x)) for x in ret]

    def __str__(self):
        ret_str = ""
        for x in self.block_to_symbol:
            ret_str += str(x) + "\t" + str(self.block_to_symbol[x]) + "\n"
        ret_str += str(self.index_slices) + "\n"
        return ret_str

    def __repr__(self):
        ret_str = ""
        for x in self.block_to_symbol:
            ret_str += str(x) + "\t" + str(self.block_to_symbol[x]) + "\n"
        ret_str += str(self.index_slices) + "\n"
        return ret_str


def check_range_const(range_const: Range):
    if z3.is_arith(range_const.left) or z3.is_arith(range_const.right):
        return True
    return not (range_const.left is not None and range_const.right is not None and range_const.left > range_const.right)


def meet(range, range_const: Range):
    if not check_range_const(range_const):
        return False
    assert range_const.const_type is not None

    if range_const.const_type == 0:
        if isinstance(range, Range):
            if range_const.left is not None and range_const.right is not None:
                return z3.Not(z3.Or(range_const.right < range.left, range.right < range_const.left))
            if range_const.right is not None:
                return z3.Or(range.left <= range_const.right, range.right <= range_const.right)
            if range_const.left is not None:
                return z3.Or(range_const.left <= range.left, range_const.left <= range.right)
            else:
                return True
        else:
            if range_const.left is not None and range_const.right is not None:
                return bool(np.all(range_const.left <= range) and np.all(range <= range_const.right))
            if range_const.right is not None:
                return bool(np.all(range <= range_const.right))
            if range_const.left is not None:
                return bool(np.all(range_const.left <= range))
            else:
                return True
    else:
        raise NotImplementedError
        # if isinstance(range, Range):
        #     if range_const.left is not None and range_const.right is not None:
        #         return z3.And(range_const.left >= range.left, range.right >= range_const.right)
        #     else:
        #         return False
        # else:
        #     return z3.And(range_const.left == range, range == range_const.right)


def meet_relation_variable(rv, range_const: Range):
    if not check_range_const(range_const):
        return False
    assert range_const.const_type is not None

    if range_const.const_type == 0:
        if range_const.left is not None and range_const.right is not None:
            return z3.And(range_const.left <= rv, rv <= range_const.right)
        if range_const.right is not None:
            return rv <= range_const.right
        if range_const.left is not None:
            return range_const.left <= rv
        else:
            return True
    else:
        raise NotImplementedError

# def str_2_linear_expression(x: str):
#     ret = []
#     x += " "
#     if x[0] != '-' and x[0] != '+':
#         x = "+" + x
#     sign = 1
#     factor = 0
#     symbol = ""
#     has_sign = False
#     has_factor = False
#     i = 0
#     while i < len(x):
#         if x[i] in ['-', '+']:
#             if x[i] == '-':
#                 sign = -1
#             else:
#                 sign = 1
#             has_sign = True
#         elif has_factor:
#             if x[i] == ' ':
#                 ret.append((sign * factor, symbol))
#                 sign = 1
#                 factor = 0
#                 symbol = ""
#                 has_sign = False
#                 has_factor = False
#             else:
#                 symbol += x[i]
#         elif has_sign:
#             if '0' <= x[i] <= '9':
#                 factor = factor * 10 + ord(x[i]) - 48
#             elif x[i] == '*':
#                 has_factor = True
#             elif x[i] != ' ':
#                 factor = 1
#                 has_factor = True
#                 symbol += x[i]
#
#         i += 1
#
#     return ret
