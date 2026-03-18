"""
Marshmallow validation schemas for API request validation.

These schemas are used by the @validate_json decorator to validate
incoming request data before it reaches the route handlers.
"""
from marshmallow import Schema, fields, validate, validates_schema, ValidationError
from transferarr.services.transfer_connection import is_torrent_transfer


# =============================================================================
# Download Client Schemas
# =============================================================================

class DownloadClientSchema(Schema):
    """Schema for POST /api/v1/download_clients"""
    name = fields.Str(required=True, validate=validate.Length(min=1, max=64))
    type = fields.Str(required=True, validate=validate.OneOf(["deluge"]))
    host = fields.Str(required=True, validate=validate.Length(min=1))
    port = fields.Int(required=True, validate=validate.Range(min=1, max=65535))
    username = fields.Str(allow_none=True, load_default=None)
    password = fields.Str(required=True)  # Required for new clients
    connection_type = fields.Str(required=True, validate=validate.OneOf(["rpc", "web"]))
    delete_cross_seeds = fields.Bool(load_default=True)


class DownloadClientUpdateSchema(Schema):
    """Schema for PUT /api/v1/download_clients/<name>
    
    Similar to DownloadClientSchema but:
    - name is not included (comes from URL path)
    - password is optional (uses stored password if not provided)
    """
    type = fields.Str(required=True, validate=validate.OneOf(["deluge"]))
    host = fields.Str(required=True, validate=validate.Length(min=1))
    port = fields.Int(required=True, validate=validate.Range(min=1, max=65535))
    username = fields.Str(allow_none=True, load_default=None)
    password = fields.Str(load_default=None)  # Optional - uses stored if not provided
    connection_type = fields.Str(required=True, validate=validate.OneOf(["rpc", "web"]))
    delete_cross_seeds = fields.Bool(load_default=True)


class DownloadClientTestSchema(Schema):
    """Schema for POST /api/v1/download_clients/test
    
    Similar to DownloadClientSchema but:
    - name is optional (only provided when editing existing client for stored password lookup)
    - password is optional (uses stored password when editing)
    """
    name = fields.Str(load_default=None)  # Optional - for stored password lookup when editing
    type = fields.Str(required=True, validate=validate.OneOf(["deluge"]))
    host = fields.Str(required=True, validate=validate.Length(min=1))
    port = fields.Int(required=True, validate=validate.Range(min=1, max=65535))
    username = fields.Str(allow_none=True, load_default=None)
    password = fields.Str(load_default=None)  # Optional - uses stored if editing existing client
    connection_type = fields.Str(required=True, validate=validate.OneOf(["rpc", "web"]))
    delete_cross_seeds = fields.Bool(load_default=True)


# =============================================================================
# Connection Schemas
# =============================================================================

class SFTPConfigSchema(Schema):
    """Schema for SFTP connection configuration.
    
    Either (host, port, username, password) OR (ssh_config_file, ssh_config_host) should be provided.
    """
    # Direct connection options
    host = fields.Str(load_default=None)
    port = fields.Int(validate=validate.Range(min=1, max=65535), load_default=22)
    username = fields.Str(load_default=None)
    password = fields.Str(load_default=None)
    private_key = fields.Str(load_default=None)
    
    # SSH config file options
    ssh_config_file = fields.Str(load_default=None)
    ssh_config_host = fields.Str(load_default=None)


class TransferConfigSideSchema(Schema):
    """Schema for one side (from/to) of a transfer configuration."""
    type = fields.Str(required=True, validate=validate.OneOf(["local", "sftp"]))
    sftp = fields.Nested(SFTPConfigSchema, load_default=None)


class TransferConfigSchema(Schema):
    """Schema for the transfer_config object (file-transfer type).
    
    Validates the from/to nested structure used by SFTP/Local file transfers.
    """
    # Use data_key to map Python's 'from_' to JSON's 'from'
    from_ = fields.Nested(TransferConfigSideSchema, required=True, data_key="from")
    to = fields.Nested(TransferConfigSideSchema, required=True)


class TorrentSourceConfigSchema(Schema):
    """Schema for torrent transfer source access configuration.
    
    Defines how Transferarr accesses .torrent files from the source Deluge's
    state directory.  ``type`` selects the access method:
    
    - ``"sftp"`` — fetch via SFTP (requires ``sftp`` block)
    - ``"local"`` — read from a locally-mounted path
    
    ``state_dir`` is the path to the Deluge state directory where
    ``{hash}.torrent`` files live.  Optional at schema level (not needed for
    connection testing), but required on save — enforced in
    ``_validate_transfer_config()`` when ``require_paths=True``.
    """
    type = fields.Str(required=True, validate=validate.OneOf(["sftp", "local"]))
    sftp = fields.Nested(SFTPConfigSchema, load_default=None)
    state_dir = fields.Str(load_default=None)

    @validates_schema
    def validate_source_config(self, data, **kwargs):
        """Cross-field validation: sftp block required for type=sftp, rejected for type=local."""
        source_type = data.get("type")
        sftp_block = data.get("sftp")
        if source_type == "sftp" and not sftp_block:
            raise ValidationError({"sftp": ["SFTP configuration is required when type is 'sftp'."]})
        if source_type == "local" and sftp_block:
            raise ValidationError({"sftp": ["SFTP configuration is not allowed when type is 'local'."]})


class TorrentTransferConfigSchema(Schema):
    """Schema for torrent transfer configuration.
    
    Validates {type: "torrent", destination_path: "...", source: {...}} structure.
    destination_path is optional — defaults at runtime to the download client's path.
    source is optional — required for private tracker torrents to fetch .torrent metadata.
    No source key = magnet-only mode.
    """
    type = fields.Str(required=True, validate=validate.Equal("torrent"))
    destination_path = fields.Str(load_default=None)
    source = fields.Nested(TorrentSourceConfigSchema, load_default=None)


def _validate_transfer_config(transfer_config: dict, require_paths: bool = True, path_data: dict = None):
    """Validate transfer_config based on its type (torrent vs file transfer).
    
    Args:
        transfer_config: The raw transfer_config dict
        require_paths: Whether to require path fields (False for test schema)
        path_data: Dict with path field values (for requiring them on file transfer)
        
    Raises:
        ValidationError: If validation fails
    """
    if is_torrent_transfer(transfer_config):
        # Validate torrent config shape
        schema = TorrentTransferConfigSchema()
        errors = schema.validate(transfer_config)
        if errors:
            raise ValidationError({"transfer_config": errors})
        # For saves (not test), source.state_dir is required when source is present
        if require_paths:
            source = transfer_config.get("source")
            if source and not source.get("state_dir"):
                raise ValidationError({
                    "transfer_config": {"source": {"state_dir": ["Missing data for required field."]}}
                })
    else:
        # Validate file transfer config shape (from/to nesting)
        schema = TransferConfigSchema()
        errors = schema.validate(transfer_config)
        if errors:
            raise ValidationError({"transfer_config": errors})
        
        # For file transfers, path fields are required
        if require_paths and path_data is not None:
            missing = []
            for field_name in [
                "source_dot_torrent_path",
                "source_torrent_download_path",
                "destination_dot_torrent_tmp_dir",
                "destination_torrent_download_path",
            ]:
                if not path_data.get(field_name):
                    missing.append(field_name)
            if missing:
                raise ValidationError({
                    f: ["Missing data for required field."]
                    for f in missing
                })


class ConnectionSchema(Schema):
    """Schema for POST /api/v1/connections
    
    Supports both file-transfer (SFTP/Local) and torrent (P2P) config shapes.
    The discriminator is transfer_config.type: if "torrent", path fields are ignored.
    Otherwise, the existing from/to nested structure is validated with required path fields.
    """
    name = fields.Str(
        required=True, 
        validate=[
            validate.Length(min=1),
            validate.Regexp(r'^[^/]+$', error="Connection name cannot contain '/'")
        ]
    )
    # Use data_key to map Python's 'from_' to JSON's 'from'
    from_ = fields.Str(required=True, data_key="from")
    to = fields.Str(required=True)
    transfer_config = fields.Dict(required=True)
    # Path fields: required for file transfers, ignored for torrent transfers
    source_dot_torrent_path = fields.Str(load_default=None)
    source_torrent_download_path = fields.Str(load_default=None)
    destination_dot_torrent_tmp_dir = fields.Str(load_default=None)
    destination_torrent_download_path = fields.Str(load_default=None)

    @validates_schema
    def validate_transfer_config(self, data, **kwargs):
        """Conditionally validate transfer_config and path fields based on transfer type."""
        transfer_config = data.get("transfer_config", {})
        _validate_transfer_config(
            transfer_config,
            require_paths=True,
            path_data=data,
        )


class ConnectionUpdateSchema(Schema):
    """Schema for PUT /api/v1/connections/<name>
    
    Similar to ConnectionSchema but:
    - name is optional (only provided for renaming)
    - Connection identified by URL path parameter
    
    Supports both file-transfer and torrent config shapes.
    """
    name = fields.Str(
        load_default=None,
        validate=[
            validate.Length(min=1),
            validate.Regexp(r'^[^/]+$', error="Connection name cannot contain '/'")
        ]
    )
    # Use data_key to map Python's 'from_' to JSON's 'from'
    from_ = fields.Str(required=True, data_key="from")
    to = fields.Str(required=True)
    transfer_config = fields.Dict(required=True)
    # Path fields: required for file transfers, ignored for torrent transfers
    source_dot_torrent_path = fields.Str(load_default=None)
    source_torrent_download_path = fields.Str(load_default=None)
    destination_dot_torrent_tmp_dir = fields.Str(load_default=None)
    destination_torrent_download_path = fields.Str(load_default=None)

    @validates_schema
    def validate_transfer_config(self, data, **kwargs):
        """Conditionally validate transfer_config and path fields based on transfer type."""
        transfer_config = data.get("transfer_config", {})
        _validate_transfer_config(
            transfer_config,
            require_paths=True,
            path_data=data,
        )


class ConnectionTestSchema(Schema):
    """Schema for POST /api/v1/connections/test
    
    Supports both file-transfer and torrent config shapes.
    Path fields are NOT required for test (not needed to test connectivity).
    """
    connection_name = fields.Str(load_default=None)  # Optional - for stored password lookup
    from_ = fields.Str(required=True, data_key="from")
    to = fields.Str(required=True)
    transfer_config = fields.Dict(required=True)

    @validates_schema
    def validate_transfer_config(self, data, **kwargs):
        """Validate transfer_config shape without requiring path fields."""
        transfer_config = data.get("transfer_config", {})
        _validate_transfer_config(
            transfer_config,
            require_paths=False,
        )


# =============================================================================
# Utility Schemas
# =============================================================================

class BrowseRequestSchema(Schema):
    """Schema for POST /api/v1/browse"""
    type = fields.Str(required=True, validate=validate.OneOf(["local", "sftp"]))
    path = fields.Str(load_default="/")
    sftp = fields.Nested(SFTPConfigSchema, load_default=None)


# =============================================================================
# Manual Transfer Schemas
# =============================================================================

class ManualTransferSchema(Schema):
    """Schema for POST /api/v1/transfers/manual

    Validates the request to initiate a manual torrent transfer.
    """
    hashes = fields.List(
        fields.Str(validate=validate.Length(min=1)),
        required=True,
        validate=validate.Length(min=1),
    )
    source_client = fields.Str(required=True, validate=validate.Length(min=1))
    destination_client = fields.Str(required=True, validate=validate.Length(min=1))
    include_cross_seeds = fields.Bool(load_default=False)
    delete_source_cross_seeds = fields.Bool(load_default=True)
