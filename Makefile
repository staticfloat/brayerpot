deploy: build
	docker-compose up --remove-orphans -d

self-update: build
	docker-compose up -d app

build:
	docker-compose build --pull

upf: build
	docker-compose up --remove-orphans

run: build
	docker-compose run app ipython

stop:
	docker-compose stop

destroy:
	docker-compose down

logs:
	docker-compose logs -f
