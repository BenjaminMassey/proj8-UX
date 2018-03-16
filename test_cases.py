import config
from pymongo import MongoClient

CONFIG = config.configuration()
client = MongoClient(CONFIG.MONGO_URL)
db = client.get_default_database()
collection = db['times']
collection.delete_many({})
testboy = {"1":"I","2":"am","3":"a","4":"test"}
print("Here I am before anything:", testboy)
collection.insert(testboy)
data = collection.find()
for datum in data:
    print("Here's 1 from the server:", datum['1'])
    print("Here's 2 from the server:", datum['2'])
    print("Here's 3 from the server:", datum['3'])
    print("Here's 4 from the server:", datum['4'])
