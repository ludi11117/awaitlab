from fractions import Fraction
from collections import Counter
from itertools import product
import math
import random
import unittest
from awaitlab.statistics import _integer_problem,_count_integer_tail,paired_randomization


def oracle(differences,tolerance):
    values=list(map(Fraction,differences));cutoff=abs(sum(values))-Fraction(tolerance)
    return sum(abs(sum(s*v for s,v in zip(signs,values)))>=cutoff
        for signs in product((-1,1),repeat=len(values)))


def count(differences):
    tolerance=max(max(map(abs,differences))*1e-12,1e-15)
    weights,cutoff=_integer_problem(differences,tolerance)
    return _count_integer_tail(weights,cutoff),tolerance


class IntegerRandomizationTests(unittest.TestCase):
    def test_fraction_oracle_with_ties_zeros_cancellation_and_binary_floats(self):
        rng=random.Random(519)
        cases=[[0.0]*8,[1,-1,1,-1],[1e100,-1e100,1,-1],
            [Fraction(1,3),Fraction(-1,2),Fraction(1,5)],
            [math.ulp(0.0),-math.ulp(0.0),0.0],
            [1.0,5e-13],[1.0,math.nextafter(5e-13,math.inf)],
            [1.0,math.nextafter(5e-13,-math.inf)]]
        for n in range(2,11):
            cases.extend([[rng.choice([-.1,.1,.3,0.0,1e-8,-1e-8]) for _ in range(n)],
                [rng.uniform(-10,10) for _ in range(n)]])
        for differences in cases:
            with self.subTest(differences=differences):
                extreme,tolerance=count(differences)
                self.assertEqual(extreme,oracle(differences,tolerance))

    def test_binomial_tail_for_32_blocks_and_zero_multiplicity(self):
        for n,negative,zeros in [(32,5,0),(31,3,1),(20,4,12)]:
            differences=[1]*negative+[-1]*(n-negative)+[0]*zeros
            actual,_=count(differences)
            expected=2*sum(math.comb(n,k) for k in range(negative+1))*2**zeros
            self.assertEqual(actual,expected)
        self.assertEqual(count([-1]*32)[0],2)
        self.assertEqual(count([1,-1]*16)[0],2**32)

    def test_distinct_power_two_distribution_has_known_uniform_tail(self):
        for n in [16,24,32]:
            differences=[float(2**i)*(1 if i%3 else -1) for i in range(n)]
            extreme,_=count(differences)
            cutoff=abs(sum(int(v) for v in differences));largest=2**n-1
            self.assertEqual(extreme,2*((largest-cutoff)//2+1))

    def test_public_exact_path_matches_fraction_oracle_and_preserves_metadata(self):
        for differences in [[.1,.3,-.1,0.0],[1.0,math.nextafter(5e-13,math.inf)]]:
            result=paired_randomization([0.0]*len(differences),differences)
            self.assertEqual(result['extreme_assignments'],oracle(differences,result['tie_tolerance']))
            self.assertEqual(result['algorithm'],'meet_in_middle_integer')
            self.assertTrue(result['exact'])
            self.assertIsNone(result['seed'])
        result=paired_randomization([10]*32,[5]*32)
        self.assertEqual(result['assignments'],2**32)
        self.assertEqual(result['extreme_assignments'],2)
        self.assertEqual(result['pvalue'],2/2**32)

    def test_monte_carlo_uses_the_same_integer_statistic_as_fraction_oracle(self):
        differences=[.1,.3,-.1,0.0,-.2]*6+[.3,-.1,.1]
        result=paired_randomization([0.0]*33,differences,seed=519,draws=200)
        values=list(map(Fraction,differences))
        cutoff=abs(sum(values))-Fraction(result['tie_tolerance']);rng=random.Random(519)
        extreme=sum(abs(sum(rng.choice((-1,1))*v for v in values))>=cutoff for _ in range(200))
        self.assertEqual(result['extreme_assignments'],extreme)
        self.assertEqual(result['pvalue'],(extreme+1)/201)
        self.assertFalse(result['exact'])
        self.assertEqual(result['algorithm'],'monte_carlo_integer')

    def test_float_sharp_null_randomized_labels_are_superuniform(self):
        weights=[.1,.3,0.0,.5,-.2]
        values=[paired_randomization([0.]*len(weights),[s*w for s,w in zip(signs,weights)])['pvalue']
            for signs in product((-1,1),repeat=len(weights))]
        for alpha in [.01,.05,.1,.25,.5]:
            self.assertLessEqual(sum(p<alpha for p in values)/len(values),alpha)

    def test_32_block_fixture_matches_independent_fraction_distribution_dp(self):
        values=[100.+(i%5-2)*.2-.15-100. for i in range(32)]
        distribution=Counter({Fraction(0):1})
        for value in map(Fraction,values):
            next_distribution=Counter()
            for partial,multiplicity in distribution.items():
                next_distribution[partial-value]+=multiplicity
                next_distribution[partial+value]+=multiplicity
            distribution=next_distribution
        result=paired_randomization([0.]*32,values)
        cutoff=abs(sum(map(Fraction,values)))-Fraction(result['tie_tolerance'])
        self.assertEqual(sum(distribution.values()),2**32)
        self.assertEqual(result['extreme_assignments'],sum(m for s,m in distribution.items() if abs(s)>=cutoff))


if __name__=='__main__':unittest.main()
