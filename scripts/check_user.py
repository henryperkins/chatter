from database import db_session
from models.user import User

def check_user(username):
    with db_session() as session:
        user = User.get_by_username(session, username)
        print(f'User exists: {user is not None}')
        if user:
            print(f'User ID: {user.id}')
            print(f'Username: {user.username}')
            print(f'Password hash exists: {bool(user.password_hash)}')
            print(f'Password hash: {user.password_hash}')
            print(f'Active: {user._active}')

if __name__ == '__main__':
    check_user('hperkins')
