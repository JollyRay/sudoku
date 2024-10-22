all:
	python manage.py runserver 5678

run:
	daphne sudoku.asgi:application

init: install
	python manage.py makemigrations
	python manage.py migrate

install:
	pip install -r requirements.txt