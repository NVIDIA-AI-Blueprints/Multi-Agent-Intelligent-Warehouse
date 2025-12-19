# Software Inventory

This document lists all third-party software packages used in this project, including their versions, licenses, authors, and sources.

**Generated:** Automatically from dependency files
**Last Updated:** 2025-12-19
**Generation Script:** `scripts/tools/generate_software_inventory.py`

## How to Regenerate

To regenerate this inventory with the latest package information:

```bash
# Activate virtual environment
source env/bin/activate

# Run the generation script
python scripts/tools/generate_software_inventory.py
```

The script automatically:
- Parses `requirements.txt`, `requirements.docker.txt`, and `scripts/requirements_synthetic_data.txt`
- Parses `pyproject.toml` for Python dependencies and dev dependencies
- Parses root `package.json` for Node.js dev dependencies (tooling)
- Parses `src/ui/web/package.json` for frontend dependencies (React, Material-UI, etc.)
- Queries PyPI and npm registries for package metadata
- Removes duplicates and formats the data into this table

## Python Packages (PyPI)

| Package Name | Version | License | License URL | Author | Source | Distribution Method | Download Location |
|--------------|---------|---------|-------------|--------|--------|---------------------|-------------------|
| aiohttp | 3.8.0 | Apache 2 | https://github.com/aio-libs/aiohttp | N/A | PyPI | pip | https://pypi.org/project/aiohttp/ |
| asyncpg | 0.29.0 | Apache License, Version 2.0 | https://pypi.org/project/asyncpg/ | MagicStack Inc <hello@magic.io> | PyPI | pip | https://pypi.org/project/asyncpg/ |
| bacpypes3 | 0.0.0 | N/A | https://pypi.org/project/bacpypes3/ | N/A | PyPI | pip | https://pypi.org/project/bacpypes3/ |
| bcrypt | 4.0.0 | Apache License, Version 2.0 | https://github.com/pyca/bcrypt/ | The Python Cryptographic Authority developers <cryptography-dev@python.org> | PyPI | pip | https://pypi.org/project/bcrypt/ |
| black | 23.0.0 | N/A | https://pypi.org/project/black/ | N/A | PyPI | pip | https://pypi.org/project/black/ |
| click | 8.0.0 | BSD-3-Clause | https://palletsprojects.com/p/click/ | Armin Ronacher <armin.ronacher@active-4.com> | PyPI | pip | https://pypi.org/project/click/ |
| email-validator | 2.0.0 | CC0 (copyright waived) | https://github.com/JoshData/python-email-validator | Joshua Tauberer <jt@occams.info> | PyPI | pip | https://pypi.org/project/email-validator/ |
| Faker | 19.0.0 | MIT License | https://github.com/joke2k/faker | joke2k <joke2k@gmail.com> | PyPI | pip | https://pypi.org/project/faker/ |
| fastapi | 0.120.0 | MIT License | https://pypi.org/project/fastapi/ | Sebastián Ramírez <tiangolo@gmail.com> | PyPI | pip | https://pypi.org/project/fastapi/ |
| fastapi | 0.104.0 | MIT License | https://pypi.org/project/fastapi/ | Sebastián Ramírez <tiangolo@gmail.com> | PyPI | pip | https://pypi.org/project/fastapi/ |
| flake8 | 6.0.0 | MIT | https://github.com/pycqa/flake8 | Tarek Ziade <tarek@ziade.org> | PyPI | pip | https://pypi.org/project/flake8/ |
| httpx | 0.27.0 | BSD License | https://pypi.org/project/httpx/ | Tom Christie <tom@tomchristie.com> | PyPI | pip | https://pypi.org/project/httpx/ |
| isort | 5.12.0 | MIT | https://pycqa.github.io/isort/ | Timothy Crosley <timothy.crosley@gmail.com> | PyPI | pip | https://pypi.org/project/isort/ |
| langchain | 0.1.0 | MIT | https://github.com/langchain-ai/langchain | N/A | PyPI | pip | https://pypi.org/project/langchain/ |
| langchain-core | 0.3.80 | MIT | https://pypi.org/project/langchain-core/ | N/A | PyPI | pip | https://pypi.org/project/langchain-core/ |
| langgraph | 0.2.30 | MIT | https://www.github.com/langchain-ai/langgraph | N/A | PyPI | pip | https://pypi.org/project/langgraph/ |
| langgraph | 0.1.0 | N/A | https://pypi.org/project/langgraph/ | N/A | PyPI | pip | https://pypi.org/project/langgraph/ |
| loguru | 0.7.0 | MIT license | https://github.com/Delgan/loguru | Delgan <delgan.py@gmail.com> | PyPI | pip | https://pypi.org/project/loguru/ |
| mypy | 1.5.0 | MIT License | https://www.mypy-lang.org/ | Jukka Lehtosalo <jukka.lehtosalo@iki.fi> | PyPI | pip | https://pypi.org/project/mypy/ |
| nemoguardrails | 0.19.0 | LICENSE.md | https://pypi.org/project/nemoguardrails/ | NVIDIA <nemoguardrails@nvidia.com> | PyPI | pip | https://pypi.org/project/nemoguardrails/ |
| numpy | 1.24.0 | BSD-3-Clause | https://www.numpy.org | Travis E. Oliphant et al. | PyPI | pip | https://pypi.org/project/numpy/ |
| numpy | 1.24.0 | BSD-3-Clause | https://www.numpy.org | Travis E. Oliphant et al. | PyPI | pip | https://pypi.org/project/numpy/ |
| paho-mqtt | 1.6.0 | Eclipse Public License v2.0 / Eclipse Distribution License v1.0 | http://eclipse.org/paho | Roger Light <roger@atchoo.org> | PyPI | pip | https://pypi.org/project/paho-mqtt/ |
| pandas | 1.2.4 | BSD | https://pandas.pydata.org | N/A | PyPI | pip | https://pypi.org/project/pandas/ |
| pandas | 2.0.0 | MIT License | https://pypi.org/project/pandas/ | The Pandas Development Team <pandas-dev@python.org> | PyPI | pip | https://pypi.org/project/pandas/ |
| passlib | 1.7.4 | BSD | https://passlib.readthedocs.io | Eli Collins <elic@assurancetechnologies.com> | PyPI | pip | https://pypi.org/project/passlib/ |
| passlib | 1.7.4 | BSD | https://passlib.readthedocs.io | Eli Collins <elic@assurancetechnologies.com> | PyPI | pip | https://pypi.org/project/passlib/ |
| pillow | 10.3.0 | HPND | https://pypi.org/project/Pillow/ | "Jeffrey A. Clark" <aclark@aclark.net> | PyPI | pip | https://pypi.org/project/Pillow/ |
| pre-commit | 3.4.0 | MIT | https://github.com/pre-commit/pre-commit | Anthony Sottile <asottile@umich.edu> | PyPI | pip | https://pypi.org/project/pre-commit/ |
| prometheus-client | 0.19.0 | Apache Software License 2.0 | https://github.com/prometheus/client_python | Brian Brazil <brian.brazil@robustperception.io> | PyPI | pip | https://pypi.org/project/prometheus-client/ |
| prometheus-client | 0.19.0 | Apache Software License 2.0 | https://github.com/prometheus/client_python | Brian Brazil <brian.brazil@robustperception.io> | PyPI | pip | https://pypi.org/project/prometheus-client/ |
| psutil | 5.9.0 | BSD | https://github.com/giampaolo/psutil | Giampaolo Rodola <g.rodola@gmail.com> | PyPI | pip | https://pypi.org/project/psutil/ |
| psycopg | 3.0 | GNU Lesser General Public License v3 (LGPLv3) | https://psycopg.org/psycopg3/ | Daniele Varrazzo <daniele.varrazzo@gmail.com> | PyPI | pip | https://pypi.org/project/psycopg/ |
| psycopg | 3.1 | GNU Lesser General Public License v3 (LGPLv3) | https://psycopg.org/psycopg3/ | Daniele Varrazzo <daniele.varrazzo@gmail.com> | PyPI | pip | https://pypi.org/project/psycopg/ |
| pydantic | 2.7.0 | MIT License | https://pypi.org/project/pydantic/ | Samuel Colvin <s@muelcolvin.com>, Eric Jolibois <em.jolibois@gmail.com>, Hasan Ramezani <hasan.r67@gmail.com>, Adrian Garcia Badaracco <1755071+adr... | PyPI | pip | https://pypi.org/project/pydantic/ |
| pydantic | 2.0 | MIT License | https://pypi.org/project/pydantic/ | Samuel Colvin <s@muelcolvin.com>, Eric Jolibois <em.jolibois@gmail.com>, Hasan Ramezani <hasan.r67@gmail.com>, Adrian Garcia Badaracco <1755071+adr... | PyPI | pip | https://pypi.org/project/pydantic/ |
| PyJWT | 2.8.0 | MIT | https://github.com/jpadilla/pyjwt | Jose Padilla <hello@jpadilla.com> | PyPI | pip | https://pypi.org/project/PyJWT/ |
| pymilvus | 2.3.0 | Apache Software License | https://pypi.org/project/pymilvus/ | Milvus Team <milvus-team@zilliz.com> | PyPI | pip | https://pypi.org/project/pymilvus/ |
| pymilvus | 2.3.0 | Apache Software License | https://pypi.org/project/pymilvus/ | Milvus Team <milvus-team@zilliz.com> | PyPI | pip | https://pypi.org/project/pymilvus/ |
| pymodbus | 3.0.0 | BSD-3-Clause | https://github.com/riptideio/pymodbus/ | attr: pymodbus.__author__ | PyPI | pip | https://pypi.org/project/pymodbus/ |
| PyMuPDF | 1.23.0 | GNU AFFERO GPL 3.0 | https://pypi.org/project/PyMuPDF/ | Artifex <support@artifex.com> | PyPI | pip | https://pypi.org/project/PyMuPDF/ |
| pyserial | 3.5 | BSD | https://github.com/pyserial/pyserial | Chris Liechti <cliechti@gmx.net> | PyPI | pip | https://pypi.org/project/pyserial/ |
| pytest | 7.4.0 | MIT | https://docs.pytest.org/en/latest/ | Holger Krekel, Bruno Oliveira, Ronny Pfannschmidt, Floris Bruynooghe, Brianna Laugher, Florian Bruhin and others | PyPI | pip | https://pypi.org/project/pytest/ |
| pytest-asyncio | 0.21.0 | Apache 2.0 | https://github.com/pytest-dev/pytest-asyncio | Tin Tvrtković <tinchester@gmail.com> <tinchester@gmail.com> | PyPI | pip | https://pypi.org/project/pytest-asyncio/ |
| pytest-cov | 4.1.0 | MIT | https://github.com/pytest-dev/pytest-cov | Marc Schlaich <marc.schlaich@gmail.com> | PyPI | pip | https://pypi.org/project/pytest-cov/ |
| python-dotenv | 1.0.0 | BSD-3-Clause | https://github.com/theskumar/python-dotenv | Saurabh Kumar <me+github@saurabh-kumar.com> | PyPI | pip | https://pypi.org/project/python-dotenv/ |
| python-dotenv | 1.0.0 | BSD-3-Clause | https://github.com/theskumar/python-dotenv | Saurabh Kumar <me+github@saurabh-kumar.com> | PyPI | pip | https://pypi.org/project/python-dotenv/ |
| python-jose | 3.3.0 | MIT | http://github.com/mpdavis/python-jose | Michael Davis <mike.philip.davis@gmail.com> | PyPI | pip | https://pypi.org/project/python-jose/ |
| python-multipart | 0.0.21 | Apache Software License | https://pypi.org/project/python-multipart/ | Andrew Dunham <andrew@du.nham.ca>, Marcelo Trylesinski <marcelotryle@gmail.com> | PyPI | pip | https://pypi.org/project/python-multipart/ |
| python-multipart | 0.0.6 | Apache Software License | https://pypi.org/project/python-multipart/ | Andrew Dunham <andrew@du.nham.ca> | PyPI | pip | https://pypi.org/project/python-multipart/ |
| PyYAML | 6.0 | MIT | https://pyyaml.org/ | Kirill Simonov <xi@resolvent.net> | PyPI | pip | https://pypi.org/project/PyYAML/ |
| redis | 5.0.0 | MIT | https://github.com/redis/redis-py | Redis Inc. <oss@redis.com> | PyPI | pip | https://pypi.org/project/redis/ |
| redis | 5.0.0 | MIT | https://github.com/redis/redis-py | Redis Inc. <oss@redis.com> | PyPI | pip | https://pypi.org/project/redis/ |
| requests | 2.32.4 | Apache-2.0 | https://requests.readthedocs.io | Kenneth Reitz <me@kennethreitz.org> | PyPI | pip | https://pypi.org/project/requests/ |
| requests | 2.31.0 | Apache 2.0 | https://requests.readthedocs.io | Kenneth Reitz <me@kennethreitz.org> | PyPI | pip | https://pypi.org/project/requests/ |
| scikit-learn | 1.5.0 | new BSD | https://scikit-learn.org | N/A | PyPI | pip | https://pypi.org/project/scikit-learn/ |
| starlette | 0.49.1 | N/A | https://pypi.org/project/starlette/ | Tom Christie <tom@tomchristie.com> | PyPI | pip | https://pypi.org/project/starlette/ |
| tiktoken | 0.12.0 | MIT License | https://pypi.org/project/tiktoken/ | Shantanu Jain <shantanu@openai.com> | PyPI | pip | https://pypi.org/project/tiktoken/ |
| uvicorn | 0.30.1 | BSD License | https://pypi.org/project/uvicorn/ | Tom Christie <tom@tomchristie.com> | PyPI | pip | https://pypi.org/project/uvicorn/ |
| uvicorn | 0.24.0 | BSD License | https://pypi.org/project/uvicorn/ | Tom Christie <tom@tomchristie.com> | PyPI | pip | https://pypi.org/project/uvicorn/ |
| websockets | 11.0 | BSD-3-Clause | https://pypi.org/project/websockets/ | Aymeric Augustin <aymeric.augustin@m4x.org> | PyPI | pip | https://pypi.org/project/websockets/ |
| xgboost | 1.6.0 | Apache-2.0 | https://github.com/dmlc/xgboost | N/A | PyPI | pip | https://pypi.org/project/xgboost/ |

## Node.js Packages (npm)

| Package Name | Version | License | License URL | Author | Source | Distribution Method | Download Location |
|--------------|---------|---------|-------------|--------|--------|---------------------|-------------------|
| @commitlint/cli | 19.8.1 | MIT | https://github.com/conventional-changelog/commitlint/blob/main/LICENSE | Mario Nebl <hello@herebecode.com> | npm | npm | https://www.npmjs.com/package/@commitlint/cli |
| @commitlint/config-conventional | 19.8.1 | MIT | https://github.com/conventional-changelog/commitlint/blob/main/LICENSE | Mario Nebl <hello@herebecode.com> | npm | npm | https://www.npmjs.com/package/@commitlint/config-conventional |
| @craco/craco | 7.1.0 | Apache-2.0 | https://github.com/dilanx/craco/blob/main/LICENSE | Dilan Nair | npm | npm | https://www.npmjs.com/package/@craco/craco |
| @emotion/react | 11.10.0 | MIT | https://github.com/emotion-js/emotion.git#main/blob/main/LICENSE | Emotion Contributors | npm | npm | https://www.npmjs.com/package/@emotion/react |
| @emotion/styled | 11.10.0 | MIT | https://github.com/emotion-js/emotion.git#main/blob/main/LICENSE | N/A | npm | npm | https://www.npmjs.com/package/@emotion/styled |
| @mui/icons-material | 5.10.0 | N/A | https://mui.com/material-ui/material-icons/ | N/A | npm | npm | https://www.npmjs.com/package/@mui/icons-material |
| @mui/material | 5.18.0 | MIT | https://github.com/mui/material-ui/blob/main/LICENSE | MUI Team | npm | npm | https://www.npmjs.com/package/@mui/material |
| @mui/x-data-grid | 7.22.0 | MIT | https://github.com/mui/mui-x/blob/main/LICENSE | MUI Team | npm | npm | https://www.npmjs.com/package/@mui/x-data-grid |
| @semantic-release/changelog | 6.0.3 | MIT | https://github.com/semantic-release/changelog/blob/main/LICENSE | Pierre Vanduynslager | npm | npm | https://www.npmjs.com/package/@semantic-release/changelog |
| @semantic-release/exec | 7.1.0 | MIT | https://github.com/semantic-release/exec/blob/main/LICENSE | Pierre Vanduynslager | npm | npm | https://www.npmjs.com/package/@semantic-release/exec |
| @semantic-release/git | 10.0.1 | MIT | https://github.com/semantic-release/git/blob/main/LICENSE | Pierre Vanduynslager | npm | npm | https://www.npmjs.com/package/@semantic-release/git |
| @semantic-release/github | 11.0.6 | MIT | https://github.com/semantic-release/github/blob/main/LICENSE | Pierre Vanduynslager | npm | npm | https://www.npmjs.com/package/@semantic-release/github |
| @tanstack/react-query | 5.90.12 | MIT | https://github.com/TanStack/query/blob/main/LICENSE | tannerlinsley | npm | npm | https://www.npmjs.com/package/@tanstack/react-query |
| @testing-library/dom | 10.4.1 | MIT | https://github.com/testing-library/dom-testing-library/blob/main/LICENSE | Kent C. Dodds <me@kentcdodds.com> | npm | npm | https://www.npmjs.com/package/@testing-library/dom |
| @testing-library/jest-dom | 5.16.4 | MIT | https://github.com/testing-library/jest-dom/blob/main/LICENSE | Ernesto Garcia <gnapse@gmail.com> | npm | npm | https://www.npmjs.com/package/@testing-library/jest-dom |
| @testing-library/react | 16.0.0 | MIT | https://github.com/testing-library/react-testing-library/blob/main/LICENSE | Kent C. Dodds <me@kentcdodds.com> | npm | npm | https://www.npmjs.com/package/@testing-library/react |
| @testing-library/user-event | 13.5.0 | MIT | https://github.com/testing-library/user-event/blob/main/LICENSE | Giorgio Polvara <polvara@gmail.com> | npm | npm | https://www.npmjs.com/package/@testing-library/user-event |
| @types/jest | 27.5.2 | MIT | https://github.com/DefinitelyTyped/DefinitelyTyped/blob/main/LICENSE | N/A | npm | npm | https://www.npmjs.com/package/@types/jest |
| @types/node | 16.11.56 | MIT | https://github.com/DefinitelyTyped/DefinitelyTyped/blob/main/LICENSE | N/A | npm | npm | https://www.npmjs.com/package/@types/node |
| @types/papaparse | 5.5.1 | MIT | https://github.com/DefinitelyTyped/DefinitelyTyped/blob/main/LICENSE | N/A | npm | npm | https://www.npmjs.com/package/@types/papaparse |
| @types/react | 19.0.0 | MIT | https://github.com/DefinitelyTyped/DefinitelyTyped/blob/main/LICENSE | N/A | npm | npm | https://www.npmjs.com/package/@types/react |
| @types/react-copy-to-clipboard | 5.0.7 | MIT | https://github.com/DefinitelyTyped/DefinitelyTyped/blob/main/LICENSE | N/A | npm | npm | https://www.npmjs.com/package/@types/react-copy-to-clipboard |
| @types/react-dom | 19.0.0 | MIT | https://github.com/DefinitelyTyped/DefinitelyTyped/blob/main/LICENSE | N/A | npm | npm | https://www.npmjs.com/package/@types/react-dom |
| @uiw/react-json-view | 2.0.0-alpha.39 | MIT | https://github.com/uiwjs/react-json-view/blob/main/LICENSE | Kenny Wang <wowohoo@qq.com> | npm | npm | https://www.npmjs.com/package/@uiw/react-json-view |
| axios | 1.8.3 | MIT | https://github.com/axios/axios/blob/main/LICENSE | Matt Zabriskie | npm | npm | https://www.npmjs.com/package/axios |
| commitizen | 4.3.1 | MIT | https://github.com/commitizen/cz-cli/blob/main/LICENSE | Jim Cummins <jimthedev@gmail.com> | npm | npm | https://www.npmjs.com/package/commitizen |
| conventional-changelog-conventionalcommits | 9.1.0 | ISC | https://github.com/conventional-changelog/conventional-changelog/blob/main/LICENSE | Ben Coe | npm | npm | https://www.npmjs.com/package/conventional-changelog-conventionalcommits |
| cz-conventional-changelog | 3.3.0 | MIT | https://github.com/commitizen/cz-conventional-changelog/blob/main/LICENSE | Jim Cummins <jimthedev@gmail.com> | npm | npm | https://www.npmjs.com/package/cz-conventional-changelog |
| date-fns | 2.29.0 | MIT | https://github.com/date-fns/date-fns/blob/main/LICENSE | N/A | npm | npm | https://www.npmjs.com/package/date-fns |
| fast-equals | 5.4.0 | MIT | https://github.com/planttheidea/fast-equals/blob/main/LICENSE | tony_quetano@planttheidea.com | npm | npm | https://www.npmjs.com/package/fast-equals |
| http-proxy-middleware | 3.0.5 | MIT | https://github.com/chimurai/http-proxy-middleware/blob/main/LICENSE | Steven Chim | npm | npm | https://www.npmjs.com/package/http-proxy-middleware |
| husky | 9.1.7 | MIT | https://github.com/typicode/husky/blob/main/LICENSE | typicode | npm | npm | https://www.npmjs.com/package/husky |
| identity-obj-proxy | 3.0.0 | MIT | https://github.com/keyanzhang/identity-obj-proxy/blob/main/LICENSE | Keyan Zhang <root@keyanzhang.com> | npm | npm | https://www.npmjs.com/package/identity-obj-proxy |
| papaparse | 5.5.3 | MIT | https://github.com/mholt/PapaParse/blob/main/LICENSE | Matthew Holt | npm | npm | https://www.npmjs.com/package/papaparse |
| react | 19.2.3 | MIT | https://github.com/facebook/react/blob/main/LICENSE | N/A | npm | npm | https://www.npmjs.com/package/react |
| react-copy-to-clipboard | 5.1.0 | MIT | https://github.com/nkbt/react-copy-to-clipboard/blob/main/LICENSE | Nik Butenko <nik@butenko.me> | npm | npm | https://www.npmjs.com/package/react-copy-to-clipboard |
| react-dom | 19.2.3 | MIT | https://github.com/facebook/react/blob/main/LICENSE | N/A | npm | npm | https://www.npmjs.com/package/react-dom |
| react-router-dom | 6.8.0 | MIT | https://github.com/remix-run/react-router/blob/main/LICENSE | Remix Software <hello@remix.run> | npm | npm | https://www.npmjs.com/package/react-router-dom |
| react-scripts | 5.0.1 | MIT | https://github.com/facebook/create-react-app/blob/main/LICENSE | N/A | npm | npm | https://www.npmjs.com/package/react-scripts |
| recharts | 2.5.0 | MIT | https://github.com/recharts/recharts/blob/main/LICENSE | recharts group | npm | npm | https://www.npmjs.com/package/recharts |
| typescript | 4.7.4 | Apache-2.0 | https://github.com/Microsoft/TypeScript/blob/main/LICENSE | Microsoft Corp. | npm | npm | https://www.npmjs.com/package/typescript |
| web-vitals | 2.1.4 | Apache-2.0 | https://github.com/GoogleChrome/web-vitals/blob/main/LICENSE | Philip Walton <philip@philipwalton.com> | npm | npm | https://www.npmjs.com/package/web-vitals |

## Notes

- **Source**: Location where the package was downloaded from (PyPI, npm)
- **Distribution Method**: Method used to install the package (pip, npm)
- **License URL**: Link to the package's license information
- Some packages may have missing information if the registry data is incomplete

## License Summary

| License | Count |
|---------|-------|
| MIT | 50 |
| MIT License | 8 |
| BSD-3-Clause | 7 |
| N/A | 5 |
| BSD | 5 |
| Apache-2.0 | 5 |
| Apache Software License | 4 |
| BSD License | 3 |
| Apache License, Version 2.0 | 2 |
| Apache Software License 2.0 | 2 |
| GNU Lesser General Public License v3 (LGPLv3) | 2 |
| Apache 2.0 | 2 |
| MIT license | 1 |
| Apache 2 | 1 |
| CC0 (copyright waived) | 1 |
| Eclipse Public License v2.0 / Eclipse Distribution License v1.0 | 1 |
| new BSD | 1 |
| HPND | 1 |
| GNU AFFERO GPL 3.0 | 1 |
| LICENSE.md | 1 |
| ISC | 1 |
