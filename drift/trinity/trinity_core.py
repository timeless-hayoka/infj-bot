from __future__ import annotations

from copy import deepcopy


class Trinity:
    def __init__(self, executive, imagine, validator):
        self.exec = executive
        self.imagine = imagine
        self.validator = validator

    def run(self, context):
        working_context = deepcopy(context or {})

        mode = self.exec.select_mode(working_context)
        weights = self.exec.allocate_weights(mode, history=working_context.get('history'))

        working_context['mode'] = mode
        working_context['weights'] = weights

        hypotheses = self.imagine.generate_hypotheses(working_context)

        validation_results = []
        validated = []
        for hypothesis in hypotheses:
            result = self.validator.validate(hypothesis, working_context.get('constraints', []))
            validation_results.append({'hypothesis': hypothesis, 'validation': result})
            if result['approved']:
                validated.append(hypothesis)

        return {
            'mode': mode,
            'weights': weights,
            'hypotheses': validated,
            'validation_results': validation_results,
            'summary': {
                'generated': len(hypotheses),
                'validated': len(validated),
                'rejected': len(hypotheses) - len(validated),
            },
        }
