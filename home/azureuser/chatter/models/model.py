                    max_allowed = provider_caps.get("max_completion_tokens", 100000)
                    if not (1 <= max_completion_tokens <= max_allowed):
                        raise ValueError(
                            f"max_completion_tokens must be between 1 and {max_allowed} for {model_type}"
                        )

            # End of validation
            return None
