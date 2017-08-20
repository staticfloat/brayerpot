deploy:
	docker-compose up --build --remove-orphans -d

build:
	docker-compose build --pull

upf:
	docker-compose up --build --remove-orphans

run:
	docker-compose run app ipython

stop:
	docker-compose stop

logs:
	docker-compose logs -f
