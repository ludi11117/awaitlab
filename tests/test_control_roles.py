from contextlib import asynccontextmanager
from dataclasses import dataclass
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from awaitlab import Arm,Experiment,Settings


# A declared role can be carried by a dataclass subtype even before the engine
# recognizes it. The regression must reach Experiment.run's actual decisions,
# rather than fail just because an older constructor has no role keyword.
@dataclass(frozen=True)
class DeclaredArm(Arm):
    role: str='candidate'


async def candidate(i):return i


@asynccontextmanager
async def workload():yield candidate


class ControlRoleTests(unittest.IsolatedAsyncioTestCase):
    async def report_for(self,control_time=50,control_output='same',blocks=8,declared=True):
        control=DeclaredArm('unchanged','replacement','sum',replacements={'sum':candidate},role='negative_control') \
            if declared else Arm('unchanged','replacement','sum',replacements={'sum':candidate})
        experiment=Experiment(workload,[Arm('fast','replacement','sum',replacements={'sum':candidate}),control],
            Settings(blocks=blocks,requests=2,warmup=0))
        async def measured(arm,trace=False):
            value=100 if arm is None else control_time if arm.name=='unchanged' else 50
            return {'latency':{'mean_ms':value,'p95_ms':value},'interventions':0,
                'replacement_calls_by_site':{'sum':2} if arm else {},
                'output_hashes':[control_output if arm and arm.name=='unchanged' else 'same']*2}
        with patch.object(experiment,'_block',side_effect=measured):return await experiment.run()

    async def test_fast_control_does_not_become_optimization_candidate(self):
        report=await self.report_for()
        control=next(c for c in report['comparisons'] if c['name']=='unchanged')
        self.assertFalse(control['candidate_improvement'])
        self.assertEqual(control['evidence_level'],'supported_in_this_experiment')
        self.assertEqual(control['control_status'],'change_detected')
        self.assertEqual(report['quality']['status'],'warning')
        self.assertFalse(report['comparisons'][0]['candidate_improvement'])

    async def test_slow_control_also_warns_without_claiming_an_improvement(self):
        report=await self.report_for(control_time=130)
        control=report['comparisons'][1]
        self.assertEqual(control['evidence_level'],'no_observed_gain')
        self.assertEqual(control['control_status'],'change_detected')
        self.assertEqual(report['quality']['status'],'warning')
        self.assertFalse(report['comparisons'][0]['candidate_improvement'])

    async def test_no_alarm_is_not_a_pass_or_equivalence_claim(self):
        report=await self.report_for(control_time=100)
        self.assertEqual(report['quality']['status'],'no_alarm_detected')
        self.assertIn('does not prove equivalence',report['quality']['scope'])
        self.assertTrue(report['comparisons'][0]['candidate_improvement'])
        self.assertFalse(report['comparisons'][1]['candidate_improvement'])
        self.assertEqual(report['evidence_policy']['family'],['fast','unchanged'])

    async def test_control_output_mismatch_withholds_other_candidates(self):
        report=await self.report_for(control_output='different')
        self.assertEqual(report['comparisons'][1]['control_status'],'output_mismatch')
        self.assertEqual(report['quality']['status'],'warning')
        self.assertFalse(report['comparisons'][0]['candidate_improvement'])

    async def test_approximate_control_is_not_reported_as_a_clean_control(self):
        report=await self.report_for(blocks=33)
        self.assertEqual(report['comparisons'][1]['control_status'],'not_assessed')
        self.assertEqual(report['quality']['status'],'inconclusive')

    async def test_name_alone_does_not_declare_a_control(self):
        report=await self.report_for(declared=False)
        self.assertEqual(report['quality']['status'],'not_checked')
        self.assertEqual(report['comparisons'][1]['role'],'candidate')
        self.assertTrue(report['comparisons'][1]['candidate_improvement'])

    async def test_captured_anomaly_replay_preserves_measured_data(self):
        from awaitlab.experiment import assess_quality
        path=Path(__file__).resolve().parents[1]/'artifacts/extended-exact-v0.7.0.json'
        original=json.loads(path.read_text(encoding='utf-8'))
        comparisons=copy.deepcopy(original['comparisons'])
        for c in comparisons:c['role']='negative_control' if c['name']=='unchanged' else 'candidate'
        quality=assess_quality(comparisons,.05,5)
        self.assertEqual(quality['status'],'warning')
        self.assertTrue(original['comparisons'][1]['candidate_improvement'])
        self.assertFalse(comparisons[1]['candidate_improvement'])
        self.assertFalse(comparisons[0]['candidate_improvement'])
        for before,after in zip(original['comparisons'],comparisons):
            for field in ['effect','randomization','holm_adjusted_p','evidence_level','blocks']:
                self.assertEqual(before[field],after[field])

    async def test_role_is_bound_to_checkpoint_identity(self):
        root=Path('D:/CodexWork/temp/awaitlab');root.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=root) as folder:
            path=Path(folder)/'role.checkpoint.json'
            settings=Settings(blocks=2,requests=2,warmup=0)
            before=Experiment(workload,[Arm('same','replacement','sum',replacements={'sum':candidate})],settings)
            after=Experiment(workload,[Arm('same','replacement','sum',replacements={'sum':candidate},role='negative_control')],settings)
            # The identity check must reject a role-only change without invoking
            # measurement, even with the same callables, settings and source file.
            from awaitlab.checkpoint import identity,write
            from dataclasses import asdict
            run_identity=identity(workload,before.arms,asdict(settings),'role-v1')
            self.assertEqual(run_identity['manifest']['arms'][0]['role'],'candidate')
            write(path,run_identity,{'same':[]},[],'running','test')
            with self.assertRaisesRegex(ValueError,'Checkpoint identity differs'):
                await after.run(checkpoint=path,resume=True,workload_version='role-v1')

    async def test_invalid_control_roles_are_rejected(self):
        for arm in [Arm('bad','replacement','sum',replacements={'sum':candidate},role='guess'),
                Arm('bad','delay','sum',delay_ms=1,role='negative_control')]:
            with self.assertRaisesRegex(ValueError,'Arm role'):
                Experiment(workload,[arm])


if __name__=='__main__':unittest.main()
