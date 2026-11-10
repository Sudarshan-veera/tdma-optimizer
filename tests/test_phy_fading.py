import numpy as np
import pytest

from tdmaopt.phy import Channel, PHY


def positions(count=120):
    return np.column_stack((np.arange(count, dtype=float), np.zeros(count)))


def test_no_fading_preserves_original_channel_power():
    pos = positions(10)
    channel = Channel(pos, PHY(), model="sinr", fading="none")

    mask = np.isfinite(channel.P)

    assert np.allclose(channel.P_effective[mask], channel.P[mask])
    assert np.allclose(channel.fading_gain[mask], 1.0)
    assert np.allclose(
        channel.lin[mask],
        10 ** (channel.P[mask] / 10),
    )


def test_rayleigh_is_reproducible_and_normalized():
    pos = positions()
    phy = PHY()

    first = Channel(
        pos, phy, model="sinr",
        fading="rayleigh", fading_seed=123
    )
    second = Channel(
        pos, phy, model="sinr",
        fading="rayleigh", fading_seed=123
    )
    third = Channel(
        pos, phy, model="sinr",
        fading="rayleigh", fading_seed=456
    )

    assert np.allclose(first.fading_gain, second.fading_gain)
    assert not np.allclose(first.fading_gain, third.fading_gain)

    values = first.fading_gain[np.triu_indices(len(pos), 1)]
    assert 0.90 < values.mean() < 1.10
    assert np.all(values >= 0)


def test_rician_is_reproducible_and_normalized():
    pos = positions()
    phy = PHY()

    first = Channel(
        pos, phy, model="sinr",
        fading="rician", rician_k=4.0, fading_seed=77
    )
    second = Channel(
        pos, phy, model="sinr",
        fading="rician", rician_k=4.0, fading_seed=77
    )

    assert np.allclose(first.fading_gain, second.fading_gain)

    values = first.fading_gain[np.triu_indices(len(pos), 1)]
    assert 0.90 < values.mean() < 1.10
    assert np.all(values >= 0)


def test_faded_power_and_linear_power_are_consistent():
    pos = positions(5)
    channel = Channel(
        pos, PHY(), model="sinr",
        fading="rayleigh", fading_seed=5
    )

    i, j = 0, 1
    expected = (
        channel.P[i, j]
        + 10 * np.log10(channel.fading_gain[i, j])
    )

    assert channel.P_effective[i, j] == pytest.approx(expected)
    assert channel.lin[i, j] == pytest.approx(
        10 ** (expected / 10)
    )


def test_fading_is_not_allowed_with_disk_model():
    with pytest.raises(ValueError):
        Channel(
            positions(5), PHY(),
            model="disk", fading="rayleigh"
        )
