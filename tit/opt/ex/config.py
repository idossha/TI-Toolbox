import os, re, sys, argparse

class ConfigError(Exception): pass

def validate_electrode(name): return bool(re.match(r'^[A-Za-z][A-Za-z0-9]*$', name))

def validate_current(value, min_val=0.0, max_val=None):
    return value > min_val and (max_val is None or value <= max_val)

def validate_env():
    required = ['PROJECT_DIR', 'SUBJECT_NAME', 'SELECTED_EEG_NET', 'LEADFIELD_HDF', 'ROI_NAME']
    config, missing = {}, []
    for var in required:
        val = os.getenv(var)
        if not val: missing.append(var)
        else: config[var] = val
    if missing: raise ConfigError(f"Missing env vars: {', '.join(missing)}")
    if not os.path.exists(config['LEADFIELD_HDF']): raise ConfigError("Leadfield file not found")
    return config

class ElectrodeConfig:
    def __init__(self, logger): self.logger = logger

    def get_config(self, all_combinations):
        # Require electrode config via environment variables
        e1_plus_env = os.getenv('E1_PLUS')
        e1_minus_env = os.getenv('E1_MINUS')
        e2_plus_env = os.getenv('E2_PLUS')
        e2_minus_env = os.getenv('E2_MINUS')

        # Check if all required environment variables are set
        missing_vars = []
        if not e1_plus_env: missing_vars.append('E1_PLUS')
        if not e1_minus_env: missing_vars.append('E1_MINUS')
        if not e2_plus_env: missing_vars.append('E2_PLUS')
        if not e2_minus_env: missing_vars.append('E2_MINUS')

        if missing_vars:
            raise ConfigError(f"Missing required environment variables: {', '.join(missing_vars)}")

        # Parse electrodes from environment variables
        electrodes = {
            'E1_plus': e1_plus_env.replace(',', ' ').split(),
            'E1_minus': e1_minus_env.replace(',', ' ').split(),
            'E2_plus': e2_plus_env.replace(',', ' ').split(),
            'E2_minus': e2_minus_env.replace(',', ' ').split()
        }

        # Validate all electrodes
        all_valid = all(
            validate_electrode(e)
            for channel in electrodes.values()
            for e in channel
        )

        if not all_valid:
            invalid_electrodes = [
                e for channel in electrodes.values()
                for e in channel
                if not validate_electrode(e)
            ]
            raise ConfigError(f"Invalid electrode names: {invalid_electrodes}")

        self.logger.info("Using electrode configuration from environment variables")

        # Handle all combinations mode
        if all_combinations:
            # In all combinations mode, all channels should use the same electrode pool
            # Check that all channels have the same electrodes
            all_electrodes = electrodes['E1_plus']
            if not all(
                electrodes[channel] == all_electrodes
                for channel in ['E1_minus', 'E2_plus', 'E2_minus']
            ):
                self.logger.warning("All combinations mode: using E1_PLUS electrodes for all channels")
            return {
                'E1_plus': all_electrodes,
                'E1_minus': all_electrodes,
                'E2_plus': all_electrodes,
                'E2_minus': all_electrodes
            }

        return electrodes

class CurrentConfig:
    def __init__(self, logger): self.logger = logger

    def get_param(self, name, default, validation_fn=None):
        try:
            import select
            if select.select([sys.stdin], [], [], 0.0)[0]:
                val = float(input().strip())
                if validation_fn is None or validation_fn(val):
                    self.logger.info(f"{name} from stdin: {val}")
                    return val
        except Exception:
            # Stdin input reading may fail - continue with environment/default values
            pass
        env_val = os.getenv(name.upper().replace(' ', '_'))
        if env_val:
            try:
                val = float(env_val)
                if validation_fn is None or validation_fn(val):
                    self.logger.info(f"{name} from env: {val}")
                    return val
            except: self.logger.warning(f"Invalid {name} in env: {env_val}")
        self.logger.info(f"{name} default: {default}")
        return default

    def get_config(self):
        total = self.get_param('total_current', 1.0, lambda x: validate_current(x, 0))
        step = self.get_param('current_step', 0.1, lambda x: validate_current(x, 0, total))
        limit = self.get_param('channel_limit', None)
        limit = limit if limit and validate_current(limit, 0, total) else None
        return {'total_current': total, 'current_step': step, 'channel_limit': limit}

def parse_args():
    # Check environment variable first
    all_combinations_env = os.getenv('ALL_COMBINATIONS')
    if all_combinations_env:
        # Create a namespace with the value from environment
        args = argparse.Namespace()
        args.all_combinations = (all_combinations_env == '1' or all_combinations_env.lower() == 'true')
        return args

    # Fallback to command-line arguments
    parser = argparse.ArgumentParser(description='TI Exhaustive Search')
    parser.add_argument('--all-combinations', action='store_true',
                       help='Search all electrode combinations')
    return parser.parse_args()

def get_full_config(logger):
    args = parse_args()
    env = validate_env()
    electrodes = ElectrodeConfig(logger).get_config(args.all_combinations)
    currents = CurrentConfig(logger).get_config()
    return {'environment': env, 'electrodes': electrodes, 'currents': currents,
           'all_combinations': args.all_combinations}
