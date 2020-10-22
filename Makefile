IMAGE_NAME = quay.io/chmouel/tekton-asa-code

image:
	@docker build -t $(IMAGE_NAME) .

push:
	@docker push $(IMAGE_NAME)

imagepush: image push

lint: ## check style with flake8
	pylint tektonasacode
