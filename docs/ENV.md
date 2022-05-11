## Environment Variables

### `MONGO_AUTH_CREDENTIALS`

Credentials to connect to your MongoDB instance. You might have to get the credentials from a team member.

**NOTE**: While setting this value in the `Production` and `Staging` environments on Github, make sure to include the value within double quotes and escape any characters using `\` as necessary. If you don't set this correctly, your deployment will fail.

This usually looks something like this:

```
MONGO_AUTH_CREDENTIALS="mongodb+srv://COLLECTION_NAME:PASSWORD@cluster0.uocfg.mongodb.net/DATABASE_NAME?retryWrites=true&w=majority"
```
