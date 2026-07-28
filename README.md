# RQUnit
RQUnit is a requirements-management framework for software built with heavy agent participation, distributed as a CLI (`rqunit`). 

> A requirement that cannot be mechanically verified is a preference. A specification
> that can drift from its code silently is decoration.

Requirements are small, individually addressable units stored beside the code they
govern, in the same version control, carrying machine-checkable links to the
artifacts that prove them. Enforcement is not advice — it is lints, consistency
checks, runtime hooks, and gates that block commits.
