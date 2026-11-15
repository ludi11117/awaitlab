import unittest
from itertools import product
from collections import Counter
from awaitlab.statistics import paired_randomization,holm_adjust,evidence_level,inference_design


class EvidenceTests(unittest.TestCase):
    def test_exact_known_all_negative_case_and_zero_case(self):
        self.assertEqual(paired_randomization([10]*6,[5]*6)['pvalue'],2/64)
        self.assertEqual(paired_randomization([10]*6,[10]*6)['pvalue'],1)
        self.assertEqual(paired_randomization([10,20],[9,21])['pvalue'],1)

    def test_holm_adjustment_restores_original_keys(self):
        adjusted=holm_adjust({'middle':.03,'small':.001,'large':.5})
        self.assertEqual(adjusted,{'small':.003,'middle':.06,'large':.5})
        for p in holm_adjust({'a':.3,'b':.31,'c':.32}).values():self.assertAlmostEqual(p,.9)

    def test_six_blocks_two_comparisons_not_enough_to_claim_support(self):
        p=paired_randomization([10]*6,[5]*6)['pvalue']
        adjusted=holm_adjust({'a':p,'b':1})
        self.assertEqual(adjusted['a'],.0625)
        self.assertEqual(evidence_level(True,-50,adjusted['a'],True,.05,5),'inconclusive')

    def test_design_floor_matches_enumerated_best_case_and_holm(self):
        for blocks in range(2,11):
            p=paired_randomization([100]*blocks,[100-i for i in range(1,blocks+1)])['pvalue']
            for family in [1,2,3,8]:
                design=inference_design(blocks,family,.05)
                self.assertEqual(design['raw_p_floor'],p)
                adjusted=holm_adjust({str(i):p for i in range(family)})
                self.assertEqual(design['holm_p_floor'],min(adjusted.values()))
                self.assertEqual(design['support_possible'],any(v<.05 for v in adjusted.values()))

    def test_resolution_boundary_is_strict_and_not_power(self):
        limited=inference_design(6,2,.0625)
        self.assertFalse(limited['support_possible'])
        self.assertEqual(limited['minimum_exact_blocks'],7)
        feasible=inference_design(7,2,.05)
        self.assertTrue(feasible['support_possible'])
        # Zero effects can never be supported even when the design has resolution.
        p=paired_randomization([10]*7,[10]*7)['pvalue']
        self.assertEqual(evidence_level(True,0,p,True,.05,5),'no_observed_gain')

    def test_design_handles_approximate_only_and_no_replacements(self):
        self.assertEqual(inference_design(17,1,.05)['status'],'approximate_only')
        self.assertIsNone(inference_design(17,1,.05)['raw_p_floor'])
        self.assertFalse(inference_design(17,1,.05)['support_possible'])
        self.assertEqual(inference_design(6,0,.05)['status'],'not_applicable')
        self.assertIsNone(inference_design(6,0,.05)['minimum_exact_blocks'])
        self.assertIsNone(inference_design(16,100000,.05)['minimum_exact_blocks'])

    def test_threshold_output_and_approximate_p_have_distinct_status(self):
        self.assertEqual(evidence_level(False,-80,.001,True,.05,5),'invalid_output')
        self.assertEqual(evidence_level(True,1,.001,True,.05,5),'no_observed_gain')
        self.assertEqual(evidence_level(True,-1,.001,True,.05,5),'below_practical_threshold')
        self.assertEqual(evidence_level(True,-80,.001,False,.05,5),'inconclusive')
        self.assertEqual(evidence_level(True,-80,.001,True,.05,5),'supported_in_this_experiment')

    def test_monte_carlo_is_seeded_and_uses_nonzero_correction(self):
        first=paired_randomization([10]*17,[5]*17,seed=81,draws=200)
        second=paired_randomization([10]*17,[5]*17,seed=81,draws=200)
        self.assertEqual(first,second)
        self.assertFalse(first['exact'])
        self.assertGreaterEqual(first['pvalue'],1/201)

    def test_exact_randomized_null_and_two_arm_family_error(self):
        # A finite sharp-null experiment: randomized labels are the only random
        # element. All 256 assignments, including ties, are equally likely.
        weights=range(1,9)
        assignments=list(product((-1,1),repeat=8))
        statistics=[abs(sum(s*w for s,w in zip(signs,weights))) for signs in assignments]
        counts=Counter(statistics)
        expected=[sum(count for value,count in counts.items() if value>=observed)/256 for observed in statistics]
        actual=[paired_randomization([100]*8,[100+s*w for s,w in zip(signs,weights)])['pvalue'] for signs in assignments]
        self.assertEqual(actual,expected)
        for alpha in [.01,.05,.1]:
            self.assertLessEqual(sum(p<alpha for p in actual)/256,alpha)
            # Independent null arms: enumerate the full product, not a Monte
            # Carlo run that might pass or fail by chance.
            rejected=sum(min(a,b)*2<alpha for a in actual for b in actual)
            self.assertLessEqual(rejected/256**2,alpha)
            # Perfectly dependent arms remain valid under Holm too.
            self.assertLessEqual(sum(holm_adjust({'a':p,'b':p})['a']<alpha for p in actual)/256,alpha)


if __name__=='__main__':unittest.main()
