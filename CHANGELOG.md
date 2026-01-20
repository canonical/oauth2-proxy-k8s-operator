# Changelog

## [2.1.0](https://github.com/canonical/oauth2-proxy-k8s-operator/compare/v2.0.0...v2.1.0) (2026-01-20)


### Features

* **jwt-bearer-token:** enable JWT bearer token handle by the ([341d98c](https://github.com/canonical/oauth2-proxy-k8s-operator/commit/341d98cde2b707d450269b52fb5f4b5c8dd03d3e))
* upgrade to use juju 1.0.0 ([638f34f](https://github.com/canonical/oauth2-proxy-k8s-operator/commit/638f34f309d9a989433ff82b28c3a0151c439055))


### Bug Fixes

* enable_jwt_bearer_token without oauth2 integration connected result in BlockedStatus ([d5f9821](https://github.com/canonical/oauth2-proxy-k8s-operator/commit/d5f9821ce6b1b8ad96567a30f611a73f1754f7e2))
* **get_extra_jwt_bearer_token:** only run if the service is running ([d3c183a](https://github.com/canonical/oauth2-proxy-k8s-operator/commit/d3c183a9a8d8024294f1b683f70eed8c78233242))
* handle missing `app_name` in relation data ([#196](https://github.com/canonical/oauth2-proxy-k8s-operator/issues/196)) ([8fbb89e](https://github.com/canonical/oauth2-proxy-k8s-operator/commit/8fbb89ef2607551548d0525f2086d753a1b26d36))
* handle missing app_name in relation data ([aebc651](https://github.com/canonical/oauth2-proxy-k8s-operator/commit/aebc651b63fd649b202d921f6d66e0963e88c0d4))
* **integration:** temporary fix ([9e90615](https://github.com/canonical/oauth2-proxy-k8s-operator/commit/9e90615b135f5092612f0fc731cd9c12e38c74f9))
* pass valid memory key to KubernetesComputeResourcesPatch ([30b42d1](https://github.com/canonical/oauth2-proxy-k8s-operator/commit/30b42d1e2563a25a634a4ffcc479589f260c11f5))
* pass valid memory key to KubernetesComputeResourcesPatch ([6a5b3ac](https://github.com/canonical/oauth2-proxy-k8s-operator/commit/6a5b3acb39cba7899193dd92e11b55e673106e08))
* remove the legacy related safe_load ([335d649](https://github.com/canonical/oauth2-proxy-k8s-operator/commit/335d649e0e41a07a76dc91fea84acd15d5a35034))
* search & replace env vars ([097d1ad](https://github.com/canonical/oauth2-proxy-k8s-operator/commit/097d1ad9991d2d9a23e32e4c149851c7038c02fb))

## [2.0.0](https://github.com/canonical/oauth2-proxy-k8s-operator/compare/v1.1.4...v2.0.0) (2025-09-18)


### ⚠ BREAKING CHANGES

* use environment variables instead of configuration file

### Bug Fixes

* add a protection to remove duplicated ingressed app names in the requirer databag ([129d716](https://github.com/canonical/oauth2-proxy-k8s-operator/commit/129d7167e54d649ac09f1467248e8ce9f7df7726))
* add a protection to remove duplicated ingressed app names in the requirer databag ([20c519f](https://github.com/canonical/oauth2-proxy-k8s-operator/commit/20c519f97d0315fb4181fb015668e0e0e9a1c999))
* update charm dependent libs ([ebc24cd](https://github.com/canonical/oauth2-proxy-k8s-operator/commit/ebc24cd84d6270b4134c2f875af00818a3a78fed))


### Code Refactoring

* use environment variables instead of configuration file ([e3169ab](https://github.com/canonical/oauth2-proxy-k8s-operator/commit/e3169ab3dab4711e2d6ae2d5663f6799bad82bc9))

## [1.1.4](https://github.com/canonical/oauth2-proxy-k8s-operator/compare/v1.1.3...v1.1.4) (2025-08-15)


### Bug Fixes

* don't restart service if config didn't change ([586541e](https://github.com/canonical/oauth2-proxy-k8s-operator/commit/586541e1800d81d671292c97429ec15914e26745))
* update charm dependent libs ([d7d14c5](https://github.com/canonical/oauth2-proxy-k8s-operator/commit/d7d14c50acc0e964c0a05063d24ddf727f874f1b))

## [1.1.3](https://github.com/canonical/oauth2-proxy-k8s-operator/compare/v1.1.2...v1.1.3) (2025-06-13)


### Bug Fixes

* add whitelist_domains config ([4965b2a](https://github.com/canonical/oauth2-proxy-k8s-operator/commit/4965b2a6b7d33bf70eda47a35fda23428fda8544))
* fix certificate transfer integration ([bf16621](https://github.com/canonical/oauth2-proxy-k8s-operator/commit/bf1662156048421c96ab00c21df0b3154e45d545))
* record app name in databag ([0c64620](https://github.com/canonical/oauth2-proxy-k8s-operator/commit/0c64620c8b4e706e6e0868965f9af7c4425a9f60))
* record app name in databag ([240e844](https://github.com/canonical/oauth2-proxy-k8s-operator/commit/240e844c59ad6e19898f9132749ced0e903792cf))

## [1.1.2](https://github.com/canonical/oauth2-proxy-k8s-operator/compare/v1.1.1...v1.1.2) (2025-05-21)


### Bug Fixes

* add pod resource constraints ([22547e7](https://github.com/canonical/oauth2-proxy-k8s-operator/commit/22547e745cdcf263ee653dd64cc0956f7b5078fc))
* address setuptools CVEs ([9be80f9](https://github.com/canonical/oauth2-proxy-k8s-operator/commit/9be80f9bb03ff7254af3aef63832b8a4cb46160f))
* address setuptools CVEs ([f6a1152](https://github.com/canonical/oauth2-proxy-k8s-operator/commit/f6a11527fc61bc6a57973b13f768d7b87d60f3fd))
* switch usptreams status code to 200 ([085d4d0](https://github.com/canonical/oauth2-proxy-k8s-operator/commit/085d4d01d92dabaa76d1eb2919495ad8690fe8c6))
* switch usptreams status code to 200 ([3da9252](https://github.com/canonical/oauth2-proxy-k8s-operator/commit/3da9252bb641068df3c3638c33795f7751157704))

## [1.1.1](https://github.com/canonical/oauth2-proxy-k8s-operator/compare/v1.1.0...v1.1.1) (2025-04-24)


### Bug Fixes

* update charm dependent libs ([672b28c](https://github.com/canonical/oauth2-proxy-k8s-operator/commit/672b28ca1d1d0ff18d3b14b11dea2f8f878d5da5))
* use identity-team workflows v1.8.5, add promote workflow ([e7a0e23](https://github.com/canonical/oauth2-proxy-k8s-operator/commit/e7a0e232a0ae94093ace0b9d27036634f4dbcdc8))

## [1.1.0](https://github.com/canonical/oauth2-proxy-k8s-operator/compare/v1.0.0...v1.1.0) (2025-04-23)


### Features

* add terraform module ([074fddb](https://github.com/canonical/oauth2-proxy-k8s-operator/commit/074fddbe66ef8d096a802336fb45d3631a58c18d))
* add the terraform module ([5bce839](https://github.com/canonical/oauth2-proxy-k8s-operator/commit/5bce839c55e599dd998c37dd66374ada45802861))
* receive ca certs ([a8665b7](https://github.com/canonical/oauth2-proxy-k8s-operator/commit/a8665b77696e7ea170eee11ab6837c00b5bb4fb4))


### Bug Fixes

* provide optional flag in charmcraft.yaml ([bb91dc0](https://github.com/canonical/oauth2-proxy-k8s-operator/commit/bb91dc0c62403ee91fc2e33e6c05227a05275abf))
* tiobe analysis ([796aca8](https://github.com/canonical/oauth2-proxy-k8s-operator/commit/796aca85062b91a1990ebf036b140d4952607f5a))
* tiobe analysis ([f4ff9f6](https://github.com/canonical/oauth2-proxy-k8s-operator/commit/f4ff9f6ab68eaa804d4b3f104ddd527cb65425a9))

## 1.0.0 (2025-03-10)


### Features

* integrate with forward-auth and auth-proxy interfaces ([e60f4a3](https://github.com/canonical/oauth2-proxy-k8s-operator/commit/e60f4a3be8a7b693cfaa793a1ab673418825ca4b))
