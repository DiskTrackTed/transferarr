"""
Movie catalog validation tests.

These tests run the full migration lifecycle for all movies in the MovieCatalog.
They are not run as part of regular test suites - only when adding new movies to the catalog.

Run with: pytest tests/test_movie_catalog.py -v -s
"""
import pytest
import time

from tests.utils import (
    clear_radarr_state,
    clear_deluge_torrents,
    clear_mock_indexer_torrents,
    movie_catalog,
)
from tests.integration.helpers import LifecycleRunner
from tests.conftest import TIMEOUTS


@pytest.mark.slow
class TestMovieCatalogLifecycle:
    """Run full migration lifecycle for all movies in the catalog."""
    
    @pytest.fixture(autouse=True)
    def setup(self, docker_services):
        """Ensure Docker services are running."""
        pass
    
    @pytest.fixture
    def lifecycle_runner(self, create_torrent, deluge_source, deluge_target, transferarr, radarr_client, sonarr_client):
        """Create a LifecycleRunner for lifecycle tests."""
        return LifecycleRunner(create_torrent, deluge_source, deluge_target, transferarr, radarr_client, sonarr_client)
    
    @pytest.mark.timeout(TIMEOUTS['torrent_transfer'] * 50)  # Allow time for many movies
    def test_all_movies_full_lifecycle(
        self,
        lifecycle_runner,
        radarr_client,
        deluge_source,
        deluge_target,
        transferarr,
    ):
        """
        Run full migration lifecycle for each movie in the catalog.
        
        This test iterates through all movies, runs the complete 7-step
        migration test for each: create torrent -> add to Radarr -> 
        queue -> download -> transfer -> verify on target.
        
        Note: This test is marked as 'slow' and should only be run when
        validating new additions to the movie catalog.
        """
        # Get all movies from catalog
        total_movies = len(movie_catalog.MOVIES)
        print(f"\n{'='*80}")
        print(f"Running full lifecycle for {total_movies} movies from catalog")
        print(f"{'='*80}\n")
        
        for idx, movie_key in enumerate(movie_catalog.MOVIES.keys(), 1):
            movie_data = movie_catalog.MOVIES[movie_key]
            movie_title = movie_data['title']
            movie_year = movie_data['year']
            tmdb_id = movie_data['tmdb_id']
            
            print(f"\n{'='*80}")
            print(f"[{idx}/{total_movies}] Testing: {movie_title} ({movie_year})")
            print(f"            Key: {movie_key}, TMDB ID: {tmdb_id}")
            print(f"{'='*80}")
            
            # Clean state before testing this movie
            transferarr.stop()
            clear_radarr_state(radarr_client)
            clear_deluge_torrents(deluge_source)
            clear_deluge_torrents(deluge_target)
            clear_mock_indexer_torrents()
            
            # Small delay to let services settle
            time.sleep(2)
            
            # Run full lifecycle test - fail immediately on first error
            lifecycle_runner.run_migration_test('radarr', movie_key=movie_key)
            print(f"\n            ✓ SUCCESS: {movie_title}")
        
        print(f"\n{'='*80}")
        print(f"✓ All {total_movies} movies completed full lifecycle successfully!")
        print(f"{'='*80}")
