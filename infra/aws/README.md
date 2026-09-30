# AWS deployment preparation — not deployed

`compute.yaml` provisions an ECS/Fargate service, HTTPS ALB, log group and task
roles in an **existing** VPC. It does not create RDS, ElastiCache, an ECR repository,
ACM certificate, secret, DNS records, NAT gateways or GitHub OIDC deploy role.
Those are explicit prerequisites; the template is not a one-command complete cloud
bootstrap. Applying it creates paid resources and requires the owner's approval.

## Before deployment
1. Approve a region, budget, network and naming plan. RDS, Redis, ALB, Fargate,
   logs and NAT/network egress may all incur charges; no cost estimate is implied.
2. Provide private RDS PostgreSQL and Redis-compatible cache endpoints, private
   subnets with necessary NAT or VPC endpoints, and two public ALB subnets.
   An existing data-client SG must be allowed into the DB/cache SGs on their ports.
3. Apply `../postgres/001-schema.sql` through an approved admin connection to a
   new database. Set unique role passwords securely. Never use the local demo
   passwords or seed real data. Schema names and roles may need integration review.
4. Create an AWS Secrets Manager JSON secret with `warehouse_url`, `audit_url`,
   `redis_url`, `api_key_hashes`. Use TLS database URLs and `rediss://` cache URLs.
   Verify database server certificates with the RDS CA bundle in staging; wire
   the approved CA/SSL configuration into the image/runtime before release.
   The template's secret permission assumes the AWS-managed Secrets Manager key;
   a customer-managed KMS key needs narrowly scoped `kms:Decrypt` permission.
5. Approve an ECR repository and initial image publication. Build from a passing
   commit, scan the image, and supply a digest or immutable tag to `ImageUri`.
6. Supply an ACM certificate and arrange a matching DNS alias after approval.
   The ALB's generated hostname will not match your certificate; use your own name.
7. Review the CloudFormation change set and its charges before execution. The
   runtime task role has no application AWS permissions. The execution role reads
   the one configuration secret and sends logs. The initial template uses demo
   planning; live-model activation is a separate approved configuration change.

## GitHub Actions
CI runs lint, local tests, real PostgreSQL/Redis integration, offline evaluation
and Docker build. `deploy.yml` is **manual only**, requires `main`, an explicit
`approve_paid_changes=true`, a successful `verify` CI check on that commit, and
uses the `production` environment. Configure required reviewers on that GitHub
environment before enabling deployment; the YAML cannot itself enforce reviewer
settings in repository administration.

Repository variables:
- `AWS_REGION`, `AWS_DEPLOY_ROLE_ARN`
- `ECR_REPOSITORY` (repository name, not URI)
- `ECS_CLUSTER`, `ECS_SERVICE`, `ECS_TASK_FAMILY`

Configure an OIDC role restricted to this repository's `production` environment,
with ECR push for the one repo, ECS registration/update/describe for this service,
and `iam:PassRole` only for the exact execution/task roles. Do not use a wildcard
administrator role or long-lived AWS access keys. Some register-task APIs need
`Resource: *`; constrain their surrounding permissions and trust policy.

The workflow builds and pushes a commit-tagged image, reads the current task
configuration, changes only the API image, registers a new revision and updates
the service. It waits for stability and checks the new revision is active so a
circuit-breaker rollback is not reported as success. No deployment workflow was
executed during authoring. CloudFormation remains the infrastructure baseline;
reconcile image parameters after CD to avoid accidentally redeploying an old image.

## Rollback and limits
ECS deployment circuit breaker enables rollback when startup/health fails. For
functional regressions, approve a rollout of the last known-good task definition.
No automatic database migration runs in CD. Keep schema changes backward compatible.

No AWS API validation, provision, deployment, HTTPS probe, image scan, load test,
backup or rollback drill has been performed here. The template was only parsed
locally. A staging deployment is required to validate IAM, routing, certificates,
secrets, image runtime and database TLS together.

## Primary references consulted
- [LangGraph StateGraph](https://reference.langchain.com/python/langgraph/graph/state/StateGraph)
- [Official MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)
- [PostgreSQL transaction defaults/timeouts](https://www.postgresql.org/docs/current/runtime-config-client.html)
- [ECS Secrets Manager injection](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/secrets-envvar-secrets-manager.html)
- [ECS Fargate task parameters](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task_definition_parameters.html)
