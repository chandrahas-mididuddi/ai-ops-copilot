# ai-ops-copilot eval results

Golden incidents: 8
Passed: 8 (100%)
Grounded citations: 8/8
Remediation match: 8/8
Approval gating correct: 8/8

| Incident | Proposed | Expected | Grounded | Match | Gating | Passed |
|----------|----------|----------|----------|-------|--------|--------|
| inc-01 | scale_checkout | scale_checkout | yes | yes | yes | yes |
| inc-02 | rollback_payments | rollback_payments | yes | yes | yes | yes |
| inc-03 | restart_inventory_worker | restart_inventory_worker | yes | yes | yes | yes |
| inc-04 | scale_notification_consumers | scale_notification_consumers | yes | yes | yes | yes |
| inc-05 | rotate_pricing_cert | rotate_pricing_cert | yes | yes | yes | yes |
| inc-06 | answer_only | answer_only | yes | yes | yes | yes |
| inc-07 | purge_pricing_cache | purge_pricing_cache | yes | yes | yes | yes |
| inc-08 | escalate_oncall | escalate_oncall | yes | yes | yes | yes |

Sensitive incidents are resumed once with an approval (action must execute) and once with a rejection (action must not execute). Both checks are included in the pass/fail above.
