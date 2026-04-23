from storage_tagger.tagger import StorageQueryTagger


def test_shoe_rack_tags():
    result = StorageQueryTagger().tag("shoe rack for entryway")
    tag_ids = set(result.tag_ids)
    assert result.domain_label == "storage_related"
    assert "obj_shoes" in tag_ids
    assert "form_rack" in tag_ids
    assert "loc_entryway" in tag_ids


def test_food_storage_container_tags():
    result = StorageQueryTagger().tag("glass food storage containers with lids")
    tag_ids = set(result.tag_ids)
    assert "obj_food" in tag_ids
    assert "form_container" in tag_ids
    assert "purpose_storage" in tag_ids
    assert "attr_glass" in tag_ids
    assert "attr_with_lid" in tag_ids


def test_under_cabinet_lighting_is_not_storage():
    result = StorageQueryTagger().tag("under cabinet lighting")
    assert result.domain_label == "not_storage"
    assert result.tag_ids == []
