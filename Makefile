build:
	#pipenv --python /opt/miniconda/envs/py38/bin/python
	pipenv install --dev
	pipenv run black *py
