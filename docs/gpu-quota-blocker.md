# Blocker log: Cloud Run GPU quota stuck at 0 on a new account

**Date:** 2026-07-07. **Status:** open. Brand-new billing account (trial signed up, activation
prepayment paid, upgraded to paid the same day), fresh project with billing linked.

## Repro

**1. GPU deploy** (per the [docs](https://docs.cloud.google.com/run/docs/configuring/services/gpu),
the first L4 deploy in a region should auto-grant 3 GPUs of quota):

```sh
cd hello-gpu
gcloud run deploy hello-gpu --source . --region us-central1 \
  --gpu 1 --gpu-type nvidia-l4 --no-gpu-zonal-redundancy \
  --cpu 4 --memory 16Gi --max-instances 1 --allow-unauthenticated
```

```
ERROR: (gcloud.run.deploy) ... You do not have quota for using GPUs without zonal redundancy.
```

Same with `--gpu-zonal-redundancy`: `You do not have quota for using GPUs with zonal redundancy.`

**2. Quota request via API** (also tried `NvidiaL4GpuAllocPerProjectRegion`, and regions
`us-east4`, `europe-west1`):

```sh
gcloud beta quotas preferences create --service=run.googleapis.com \
  --quota-id=NvidiaL4GpuAllocNoZonalRedundancyPerProjectRegion \
  --preferred-value=1 --dimensions=region=us-central1 \
  --project=<project id> --email=<account email>
```

```
"grantedValue": "0",
"stateDetail": "We cannot grant the preferred quota '1' ... at this moment. '0' was granted."
```

**3. Quota request via console:** IAM & Admin → Quotas & System Limits → filter
`NvidiaL4GpuAllocNoZonalRedundancy` + `us-central1` → row menu (⋮) → Edit quota.
The panel refuses input:

> Enter a new quota value between 0 and 0. Based on your service usage history, you are not
> eligible for a quota increase at this time.

![Cloud console quota edit panel locked at 0](cloud-run-gpu-quota-blocked.png)

## Diagnosis

Free-trial accounts [can't use GPUs or request quota increases](https://docs.cloud.google.com/free/docs/free-cloud-features).
Upgrading to paid is supposed to lift that immediately, but there is a trust/propagation lag
(roughly 24 to 48 hours per support replies; [one report](https://discuss.google.dev/t/cloud-run-gpu-quota-not-activated-after-50-hours-on-paid-account/323795)
still waited at 50+ hours; [same wall here](https://discuss.google.dev/t/300-free-trial-is-useless-without-gpu-quota-my-trial-period-is-wasting-away/290091)).

## Escalation attempts

I also tried escalating this to sales and support, but none of the options I tried quite worked.

## Update (2026-07-08): GPU gate lifted in us-central1, memory quota is the new blocker

About a day after the paid upgrade, the us-central1 deploy stopped failing on GPU quota.
Re-running the same deploy command from the repro above:

```sh
cd hello-gpu
gcloud run deploy hello-gpu --source . --region us-central1 \
  --gpu 1 --gpu-type nvidia-l4 --no-gpu-zonal-redundancy \
  --cpu 4 --memory 16Gi --max-instances 1 --allow-unauthenticated
```

It now fails on memory instead:

```
Quota violated:
MemAllocPerProjectRegion requested: 51539607552 allowed: 42949672960
```

That's 48 GiB requested vs 40 GiB allowed: Cloud Run requires at least 16 GiB of RAM on any
instance with a GPU attached, and the
[first-deploy auto-grant](https://docs.cloud.google.com/run/docs/configuring/services/gpu)
comes as a fixed bundle of 3 GPUs.

Swept all five publicly available L4 regions (the docs list a sixth, asia-south1, but it's
invitation-only), both redundancy modes:

| Region | No zonal redundancy | Zonal redundancy |
|---|---|---|
| us-central1 | memory quota (past the GPU gate) | GPU quota 0 |
| us-east4 | GPU quota 0 | GPU quota 0 |
| europe-west1 | GPU quota 0 | GPU quota 0 |
| europe-west4 | GPU quota 0 | GPU quota 0 |
| asia-southeast1 | GPU quota 0 | GPU quota 0 |

Also requested quota increases directly. The us-central1 memory cap from 40 GiB to 64 GiB:

```sh
gcloud beta quotas preferences create --service=run.googleapis.com \
  --quota-id=MemAllocPerProjectRegion \
  --preferred-value=68719476736 --dimensions=region=us-central1 \
  --project=<project id> --email=<account email>
```

```
"We cannot grant the preferred quota '68719476736' for limit 'MemAllocPerProjectRegion'
in service 'run.googleapis.com' at this moment. '42949672960' was granted."
```

The console marks the memory quota ineligible for increase: `NOT_ENOUGH_USAGE_HISTORY`.
