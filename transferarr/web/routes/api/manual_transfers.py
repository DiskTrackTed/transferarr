"""
Manual transfer routes for initiating user-driven torrent transfers.
"""
from flask import current_app, request
from transferarr.web.services import ManualTransferService, NotFoundError, ValidationError
from transferarr.web.schemas import ManualTransferSchema
from .responses import success_response, error_response, server_error_response, validation_error_response
from .validation import validate_json
import logging

logger = logging.getLogger("transferarr")


def register_routes(bp):
    """Register manual transfer routes with the given blueprint."""

    @bp.route("/transfers/destinations")
    def get_destinations():
        """Get valid destination clients for a source client.
        ---
        tags:
          - Transfers
        parameters:
          - in: query
            name: source
            type: string
            required: true
            description: Name of the source download client
        responses:
          200:
            description: List of valid destination clients
            schema:
              type: object
              properties:
                data:
                  type: array
                  items:
                    type: object
                    properties:
                      client:
                        type: string
                        description: Destination client name
                      connection:
                        type: string
                        description: Connection name
                      transfer_type:
                        type: string
                        enum: [file, torrent]
                        description: Transfer method
          400:
            description: Missing source parameter
          404:
            description: Source client not found
          500:
            description: Server error
        """
        try:
            source = request.args.get("source")
            if not source:
                return validation_error_response("'source' query parameter is required")

            service = ManualTransferService(current_app.config["TORRENT_MANAGER"])
            destinations = service.get_destinations(source)
            return success_response(destinations)
        except NotFoundError as e:
            return error_response(
                f"{e.resource_type.upper()}_NOT_FOUND",
                str(e),
                status_code=404,
            )
        except Exception as e:
            logger.error(f"Error getting destinations: {e}")
            return server_error_response(str(e))

    @bp.route("/transfers/manual", methods=["POST"])
    @validate_json(ManualTransferSchema)
    def initiate_manual_transfer():
        """Initiate a manual torrent transfer.
        ---
        tags:
          - Transfers
        parameters:
          - in: body
            name: body
            required: true
            schema:
              type: object
              required:
                - hashes
                - source_client
                - destination_client
              properties:
                hashes:
                  type: array
                  items:
                    type: string
                  description: List of torrent hashes to transfer
                source_client:
                  type: string
                  description: Name of the source download client
                destination_client:
                  type: string
                  description: Name of the destination download client
                include_cross_seeds:
                  type: boolean
                  default: false
                  description: Whether to auto-include cross-seed siblings
                delete_source_cross_seeds:
                  type: boolean
                  default: true
                  description: Whether to remove cross-seed siblings from source when the torrent is removed after transfer
        responses:
          200:
            description: Transfer initiated successfully
            schema:
              type: object
              properties:
                data:
                  type: object
                  properties:
                    initiated:
                      type: array
                      items:
                        type: object
                        properties:
                          hash:
                            type: string
                          name:
                            type: string
                          method:
                            type: string
                    errors:
                      type: array
                      items:
                        type: object
                    total_initiated:
                      type: integer
                    total_errors:
                      type: integer
                message:
                  type: string
          400:
            description: Validation error
          404:
            description: Client or connection not found
          500:
            description: Server error
        """
        try:
            service = ManualTransferService(current_app.config["TORRENT_MANAGER"])
            result = service.validate_and_initiate(request.validated_data)

            msg = f"Initiated {result['total_initiated']} transfer(s)"
            if result["total_errors"] > 0:
                msg += f" with {result['total_errors']} error(s)"

            return success_response(result, msg)
        except ValidationError as e:
            return validation_error_response(str(e), e.details if hasattr(e, "details") else None)
        except NotFoundError as e:
            return error_response(
                f"{e.resource_type.upper()}_NOT_FOUND",
                str(e),
                status_code=404,
            )
        except Exception as e:
            logger.error(f"Error initiating manual transfer: {e}")
            return server_error_response(str(e))
