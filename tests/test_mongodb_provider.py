"""
The tests for the mongodb storage provider
"""

import uuid

from decouple import config
from django.contrib.auth import get_user_model
from django.test import TestCase
from pydantic import ValidationError
from sqooler.schemes import MongodbLoginInformation
from sqooler.storage_providers.mongodb import MongodbProviderExtended as MongodbProvider

from qlued.models import StorageProviderDb
from qlued.storage_providers import get_short_backend_name

User = get_user_model()


class MongodbProviderTest(TestCase):
    """
    The class that contains all the tests for the dropbox provider.
    """

    def setUp(self):
        """
        set up the test.
        """
        # load the credentials from the environment through decouple

        # create a user
        self.username = config("USERNAME_TEST")
        self.password = config("PASSWORD_TEST")
        user = User.objects.create(username=self.username)
        user.set_password(self.password)
        user.save()
        self.user = user

        # put together the login information
        mongodb_username = config("MONGODB_USERNAME")
        mongodb_password = config("MONGODB_PASSWORD")
        mongodb_database_url = config("MONGODB_DATABASE_URL")

        login_dict = {
            "mongodb_username": mongodb_username,
            "mongodb_password": mongodb_password,
            "mongodb_database_url": mongodb_database_url,
        }

        # create the storage entry in the models
        mongodb_entry = StorageProviderDb.objects.create(
            storage_type="mongodb",
            name="mongodbtest",
            owner=self.user,
            description="MongoDB storage provider for tests",
            login=login_dict,
            is_active=True,
        )
        mongodb_entry.full_clean()
        mongodb_entry.save()

    def tearDown(self) -> None:
        """
        Clean out the mongodb database.
        """
        # Remove all the collections that start with queued.
        mongodb_entry = StorageProviderDb.objects.get(name="mongodbtest")
        login_info = MongodbLoginInformation(**mongodb_entry.login)
        storage_provider = MongodbProvider(login_info, mongodb_entry.name)
        database = storage_provider.client["jobs"]
        for collection_name in database.list_collection_names():
            if collection_name.startswith("queued.dummy"):
                collection = database[collection_name]
                collection.drop()

        # Remove all the collections from results that start with dummy
        database = storage_provider.client["results"]
        for collection_name in database.list_collection_names():
            if collection_name.startswith("dummy"):
                collection = database[collection_name]
                collection.drop()

        # Remove all the collections from status that start with dummy
        database = storage_provider.client["status"]
        for collection_name in database.list_collection_names():
            if collection_name.startswith("dummy"):
                collection = database[collection_name]
                collection.drop()

    def test_mongodb_object(self):
        """
        Test that we can create a MongoDB object.
        """
        mongodb_entry = StorageProviderDb.objects.get(name="mongodbtest")
        login_info = MongodbLoginInformation(**mongodb_entry.login)
        mongodb_provider = MongodbProvider(login_info, mongodb_entry.name)

        self.assertIsNotNone(mongodb_provider)

        # test that we cannot create a dropbox object a poor login dict structure
        poor_login_dict = {
            "app_key_t": "test",
            "app_secret": "test",
            "refresh_token": "test",
        }
        with self.assertRaises(ValidationError):
            login_info = MongodbLoginInformation(**poor_login_dict)
            MongodbProvider(login_info, mongodb_entry.name)

    def test_not_active(self):
        """
        Test that we cannot work with the provider if it is not active.
        """
        entry = StorageProviderDb.objects.get(name="mongodbtest")
        entry.is_active = False
        login_info = MongodbLoginInformation(**entry.login)
        storage_provider = MongodbProvider(login_info, entry.name, entry.is_active)

        # make sure that we cannot upload if it is not active
        test_content = {"experiment_0": "Nothing happened here."}
        storage_path = "test/subcollection"

        job_id = uuid.uuid4().hex[:24]
        second_path = "test/subcollection_2"
        with self.assertRaises(ValueError):
            storage_provider.upload(test_content, storage_path, job_id)
        with self.assertRaises(ValueError):
            storage_provider.get(storage_path, job_id)
        with self.assertRaises(ValueError):
            storage_provider.move(storage_path, second_path, job_id)
        with self.assertRaises(ValueError):
            storage_provider.delete(second_path, job_id)

    def test_upload_etc(self):
        """
        Test that it is possible to upload a file.
        """

        # create a mongodb object
        mongodb_entry = StorageProviderDb.objects.get(name="mongodbtest")
        login_info = MongodbLoginInformation(**mongodb_entry.login)
        storage_provider = MongodbProvider(login_info, mongodb_entry.name)

        # upload a file and get it back
        test_content = {"experiment_0": "Nothing happened here."}
        storage_path = "test/subcollection"

        job_id = uuid.uuid4().hex[:24]
        storage_provider.upload(test_content, storage_path, job_id)
        test_result = storage_provider.get(storage_path, job_id)

        self.assertDictEqual(test_content, test_result)

        # move it and get it back
        second_path = "test/subcollection_2"
        storage_provider.move(storage_path, second_path, job_id)
        test_result = storage_provider.get(second_path, job_id)
        self.assertDictEqual(test_content, test_result)

        # clean up our mess
        storage_provider.delete(second_path, job_id)

    def test_backend_name(self):
        """
        Test that we separate out properly the backend names
        """
        short_test_name = "tests"
        short_name = get_short_backend_name(short_test_name)

        self.assertEqual(short_test_name, short_name)

        test_name = "alqor_tests_simulator"
        short_name = get_short_backend_name(test_name)
        self.assertEqual(short_test_name, short_name)

        test_name = "alqor_tests_simulator_crap"
        short_name = get_short_backend_name(test_name)
        self.assertEqual("", short_name)
