Traceback (most recent call last)
File "/home/azureuser/docs/pip/lib/python3.12/site-packages/flask/app.py", line 2213, in __call__
    def __call__(self, environ: dict, start_response: t.Callable) -> t.Any:
        """The WSGI server calls the Flask application object as the
        WSGI application. This calls :meth:`wsgi_app`, which can be
        wrapped to apply middleware.
        """
        return self.wsgi_app(environ, start_response)
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
File "/home/azureuser/docs/pip/lib/python3.12/site-packages/flask/app.py", line 2193, in wsgi_app
            try:
                ctx.push()
                response = self.full_dispatch_request()
            except Exception as e:
                error = e
                response = self.handle_exception(e)
                           ^^^^^^^^^^^^^^^^^^^^^^^^
            except:  # noqa: B001
                error = sys.exc_info()[1]
                raise
            return response(environ, start_response)
        finally:
File "/home/azureuser/docs/pip/lib/python3.12/site-packages/flask/app.py", line 2190, in wsgi_app
        ctx = self.request_context(environ)
        error: BaseException | None = None
        try:
            try:
                ctx.push()
                response = self.full_dispatch_request()
                           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^
            except Exception as e:
                error = e
                response = self.handle_exception(e)
            except:  # noqa: B001
                error = sys.exc_info()[1]
File "/home/azureuser/docs/pip/lib/python3.12/site-packages/flask/app.py", line 1486, in full_dispatch_request
            request_started.send(self, _async_wrapper=self.ensure_sync)
            rv = self.preprocess_request()
            if rv is None:
                rv = self.dispatch_request()
        except Exception as e:
            rv = self.handle_user_exception(e)
                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
        return self.finalize_request(rv)
 
    def finalize_request(
        self,
        rv: ft.ResponseReturnValue | HTTPException,
File "/home/azureuser/docs/pip/lib/python3.12/site-packages/flask/app.py", line 1484, in full_dispatch_request
 
        try:
            request_started.send(self, _async_wrapper=self.ensure_sync)
            rv = self.preprocess_request()
            if rv is None:
                rv = self.dispatch_request()
                     ^^^^^^^^^^^^^^^^^^^^^^^
        except Exception as e:
            rv = self.handle_user_exception(e)
        return self.finalize_request(rv)
 
    def finalize_request(
File "/home/azureuser/docs/pip/lib/python3.12/site-packages/flask/app.py", line 1469, in dispatch_request
            and req.method == "OPTIONS"
        ):
            return self.make_default_options_response()
        # otherwise dispatch to the handler for that endpoint
        view_args: dict[str, t.Any] = req.view_args  # type: ignore[assignment]
        return self.ensure_sync(self.view_functions[rule.endpoint])(**view_args)
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
 
    def full_dispatch_request(self) -> Response:
        """Dispatches the request and on top of that performs request
        pre and postprocessing as well as HTTP exception catching and
        error handling.
File "/home/azureuser/docs/pip/lib/python3.12/site-packages/flask_login/utils.py", line 290, in decorated_view
            return current_app.login_manager.unauthorized()Open an interactive python shell in this frame
 
        # flask 1.x compatibility
        # current_app.ensure_sync is only available in Flask >= 2.0
        if callable(getattr(current_app, "ensure_sync", None)):
            return current_app.ensure_sync(func)(*args, **kwargs)
                   ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
        return func(*args, **kwargs)
 
    return decorated_view
 
 
File "/home/azureuser/chatter/routes/chat_routes.py", line 99, in new_chat_route
    # Ensure current_user.id is an integer
    user_id = int(current_user.id)
    # Ensure chat_id is a string
    chat_id = str(chat_id)
    # Create a new chat in the database
    Chat.create(chat_id, user_id, "New Chat")
    ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    session["chat_id"] = chat_id
    # Add the default message to the conversation
    conversation_manager.add_message(
        chat_id, "user", "Please format your responses in Markdown."
    )
File "/home/azureuser/chatter/models.py", line 107, in create
 
    @staticmethod
    def create(chat_id, user_id, title):
        """Create a new chat."""
        db = get_db()
        db.execute(
        ^
            "INSERT INTO chats (id, user_id, title) VALUES (?, ?, ?)",
            (chat_id, user_id, title),
        )
        db.commit()
        logger.info(f"Chat created: {chat_id} for user {user_id}")
sqlite3.IntegrityError: datatype mismatch 
