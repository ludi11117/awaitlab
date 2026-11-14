import unittest
from awaitlab.statistics import paired_randomization,holm_adjust,evidence_level


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


if __name__=='__main__':unittest.main()
