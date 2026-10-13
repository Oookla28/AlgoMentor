from django.contrib.auth import get_user_model
from django.test import TestCase
from apps.problems.models import CodeDraft, Problem, Submission, ExecutionRequest
from apps.learning.models import MasteryState, LearningActivity


class PrivateCodeDraftTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='draft-owner', password='test-password')
        self.other = get_user_model().objects.create_user(username='draft-other', password='test-password')
        self.problem = Problem.objects.create(slug='draft-problem', title='草稿测试', description='test', input_description='', output_description='', reference_solution='print(1)', reference_complexity='O(1)')
        self.client.force_login(self.user)

    def save(self, **overrides):
        return self.client.post('/api/v1/code/draft/', data={'problem_id': self.problem.pk, 'code': 'print(1)', 'stdin': 'a', **overrides}, content_type='application/json')

    def test_save_and_load_without_execution_or_learning_evidence(self):
        response = self.save()
        self.assertEqual(response.status_code, 200)
        data = self.client.get('/api/v1/code/draft/', {'problem_id': self.problem.pk}).json()['data']
        self.assertIn('no-store', response['Cache-Control'])
        self.assertTrue(data['saved'])
        self.assertEqual(data['code'], 'print(1)')
        self.assertEqual(Submission.objects.count(), 0)
        self.assertEqual(ExecutionRequest.objects.count(), 0)
        self.assertEqual(LearningActivity.objects.count(), 0)
        self.assertEqual(MasteryState.objects.count(), 0)

    def test_private_across_users_and_problem_lab_scopes(self):
        self.save()
        self.client.force_login(self.other)
        self.assertFalse(self.client.get('/api/v1/code/draft/', {'problem_id': self.problem.pk}).json()['data']['saved'])
        self.save(code='print(2)')
        self.client.force_login(self.user)
        self.assertEqual(self.client.get('/api/v1/code/draft/', {'problem_id': self.problem.pk}).json()['data']['code'], 'print(1)')
        self.assertFalse(self.client.get('/api/v1/code/draft/').json()['data']['saved'])
        self.save(problem_id=None, code='print(3)')
        self.assertEqual(CodeDraft.objects.count(), 3)

    def test_manual_update_keeps_one_draft(self):
        self.save()
        self.save(code='print(9)')
        self.assertEqual(CodeDraft.objects.count(), 1)
        self.assertEqual(CodeDraft.objects.get().code, 'print(9)')

    def test_requires_authenticated_user(self):
        self.client.logout()
        self.assertEqual(self.client.get('/api/v1/code/draft/').status_code, 401)
        self.assertEqual(self.save().status_code, 401)

    def test_validates_scope_and_utf8_size(self):
        self.assertEqual(self.save(problem_id=True).status_code, 400)
        self.assertEqual(self.save(problem_id='bad').status_code, 400)
        self.assertEqual(self.save(problem_id=1.2).status_code, 400)
        self.assertEqual(self.save(code=['bad']).status_code, 400)
        self.assertEqual(self.save(code='中' * 22000).status_code, 400)
        self.assertEqual(self.save(stdin='中' * 11000).status_code, 400)

    def test_csrf_is_required_for_draft_mutations(self):
        from django.test import Client
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        self.assertEqual(client.post('/api/v1/code/draft/', data={'code': 'print(1)'}, content_type='application/json').status_code, 403)
