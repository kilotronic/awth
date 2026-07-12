.PHONY: build-local push-local

build-local:
	podman build -t awth:local .
	@echo "Built awth:local - ready to use in other projects"

push-local:
	podman tag awth:local localhost:5000/awth:latest
	podman push localhost:5000/awth:latest
