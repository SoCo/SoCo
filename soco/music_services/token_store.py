"""This module implements token stores for the music services

A user can provide their own token store depending on how that person
wish to save the tokens, or use the builtin token store (the default)
which saves the tokens in a config file.

"""

from os import path, makedirs
import json
import appdirs


class TokenStoreBase:
    """Token store base class"""

    def __init__(self, token_collection="default"):
        """Instantiate instance variables"""
        self.token_collection = token_collection

    def save_token_pair(self, music_service_id, token_pair):
        """Save a token value pair (token, key) which is a 2 item sequence"""
        raise NotImplementedError

    def load_token_pair(self, music_service_id):
        """Load a token pair (token, key) which is a (2 item sequence)"""
        raise NotImplementedError


class JsonFileTokenStore(TokenStoreBase):

    def __init__(self, filepath, token_collection="default"):
        """Instantiate instance variables"""
        super().__init__(token_collection=token_collection)
        self.filepath = filepath
        try:
            with open(self.filepath) as file_:
                self._token_store = json.load(file_)
        except FileNotFoundError:
            self._token_store = {}

    @classmethod
    def from_config_file(cls, token_collection="default"):
        """Load from file in config directory location"""
        config_dir = appdirs.user_config_dir("SoCo", "SoCoGroup")
        config_file = path.join(config_dir, "token_store.json")
        return cls(config_file, token_collection=token_collection)

    def save_collection(self):
        """Save the collection to a config file"""
        folder = path.dirname(self.filepath)
        if not path.exists(folder):
            makedirs(folder)
        with open(self.filepath, "w") as file_:
            json.dump(self._token_store, file_, indent=4)

    def save_token_pair(self, music_service_id, token_pair):
        """Save a token value pair (token, key) which is a 2 item sequence"""
        if self.token_collection not in self._token_store:
            self._token_store[self.token_collection] = {}
        self._token_store[self.token_collection][music_service_id] = list(token_pair)
        self.save_collection()

    def load_token_pair(self, music_service_id):
        """Load a token pair (token, key) which is a (2 item sequence)"""
        return self._token_store.get(self.token_collection, {})[music_service_id]

    def has_token(self, music_service_id):
        """Return True if a token is stored for the music service"""
        return music_service_id in self._token_store.get(self.token_collection, {})



if __name__ == "__main__":
    ts = JsonFileTokenStore.from_config_file()
    print(ts)
    print(ts._token_store)
    #ts.load_token_pair("714")
    #ts.save_token_pair("714", ("jjjj", "kkkk"))
    
    

