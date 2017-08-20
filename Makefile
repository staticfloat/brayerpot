deploy: build
	docker-compose up --remove-orphans -d

build:
	docker-compose build --pull

upf: build
	docker-compose up --remove-orphans

run: build
	docker-compose run app ipython

stop:
	docker-compose stop

logs:
	docker-compose logs -f
