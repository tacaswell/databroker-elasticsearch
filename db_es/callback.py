#!/usr/bin/env python3

"""Callback for adding data to elastic search from run engine """

from bluesky.callbacks.core import CallbackBase
from elasticsearch import Elasticsearch
from elasticsearch import helpers as eshelpers

noconversion = lambda x: x


def toisoformat(epoch):
    """Convert epoch seconds to elasticsearch friendly ISO time.

    When `epoch` is a float return ISO date with millisecond
    precision.  Otherwise return date rounded to seconds.

    Parameters
    ----------
    epoch : float
        The time in seconds since POSIX epoch in 1970.

    Returns
    -------
    isodate : str
        The ISO formatted date and time with second or millisecond precision.
    """
    from datetime import datetime
    epochms = round(epoch, 3)
    dt = datetime.fromtimestamp(epochms)
    tiso = dt.isoformat()
    rv = tiso[:-3] if dt.microsecond else tiso
    assert len(rv) in (19, 23)
    return rv


def normalize_counts(d):
    if not isinstance(d, dict):
        return None
    totalcount = sum(d.values()) or 1.0
    rv = dict((k, v / totalcount) for k, v in d.items())
    return rv


def listofstrings(v):
    rv = None
    if isinstance(v, list) and all(isinstance(w, str) for w in v):
        rv = v
    return rv


DOCMAP = {}

DOCMAP['iss'] = [
    # mongoname  esname  converter
    ("_id", "issid", str),
    ("comment", "comment", noconversion),
    ("cycle", "cycle", int),
    ("detectors", "detectors", noconversion),
    ("e0", "e0", noconversion),
    ("edge", "edge", noconversion),
    ("element", "element", noconversion),
    ("experiment", "experiment", noconversion),
    ("group", "group", noconversion),
    ("name", "name", noconversion),
    ("num_points", "num_points", noconversion),
    ("plan_name", "plan_name", noconversion),
    ("PI", "pi", noconversion),
    ("PROPOSAL", "proposal", noconversion),
    ("SAF", "saf", noconversion),
    ("scan_id", "scan_id", noconversion),
    ("time", "time", noconversion),
    ("trajectory_name", "trajectory_name", noconversion),
    ("uid", "uid", noconversion),
    ("year", "year", int),
    ("time", "date", toisoformat),
]

DOCMAP['xpd'] = [
    # mongoname  esname  converter
    ("_id", "xpdid", str),
    ("bt_experimenters", "experimenters", listofstrings),
    ("bt_piLast", "pi", noconversion),
    ("bt_safN", "saf", str),
    ("bt_wavelength", "wavelength", float),
    ("composition_string", "formula", noconversion),
    ("dark_frame", "dark_frame", bool),
    ("group", "group", noconversion),
    ("lead_experimenter", "pi", noconversion),
    ("notes", "comment", noconversion),
    ("num_points", "num_points", noconversion),
    ("plan_name", "plan_name", noconversion),
    ("sample_composition", "composition", normalize_counts),
    ("scan_id", "scan_id", noconversion),
    ("sp_computed_exposure", "sp_computed_exposure", float),
    ("sp_num_frames", "sp_num_frames", int),
    ("sp_plan_name", "sp_plan_name", noconversion),
    ("sp_time_per_frame", "sp_time_per_frame", float),
    ("sp_type", "sp_type", noconversion),
    ("time", "time", noconversion),
    ("time", "date", toisoformat),
    ("uid", "uid", noconversion),
    ("time", "year", lambda t: int(toisoformat(t)[:4])),
]

DOCFILTER = {
    'iss': {},
    'xpd': {
        # limit to XPD beamline stuff and Billinge relations
        '$or': [
            {'bt_piLast': {'$exists': False}},
            {'bt_piLast': {'$in': (
                '0713_test',
                'Abeykoon',
                'Antonaropoulos',
                'Assefa',
                'Banerjee',
                'Benjiamin',
                'Billinge',
                'Bordet',
                'Bozin',
                'Demo',
                'Dooryhee',
                'Frandsen',
                'Ghose',
                'Hanson',
                'Milinda and Runze',
                'Milinda',
                'Pinero',
                'Robinson',
                'Sanjit',
                'Shi',
                'Test',
                'Yang',
                'billinge',
                'simulation',
                'test',
                'testPI',
                'testPI_2',
                'testTake2',
                'xpdAcq_realase',
            )}}
        ]},
}


def esdocument(docmap, entry):
    rv = {}
    assert '_id' in entry
    for mname, esname, fcnv in docmap:
        if not mname in entry:
            continue
        mvalue = entry[mname]
        evalue = fcnv(mvalue) if mvalue is not None else None
        if evalue is None:
            continue
        rv[esname] = evalue
    return rv


class ElasticInsert(CallbackBase):
    def __init__(self, es_config, docmap, beamline, criteria=None):
        self.criteria = criteria
        self.beamline = beamline
        self.es_config = es_config
        self.docmap = docmap
        self.es = Elasticsearch()

    def start(self, doc):
        if self.criteria and self.criteria(doc):
            esindex = self.es_config['index']
            # filter the doc
            # transform the docs
            sanitized_docs = esdocument(self.docmap, doc)
            actions = dict(_index=esindex,
                           # XXX: this might not work?
                           _id=doc['uid'],
                           _type=self.beamline, _source=sanitized_docs)
            self.es.indices.delete(index=esindex, ignore_unavailable=True)
            self.es.indices.create(index=esindex)
            mbody = {"properties": {
                "time": {"type": "date", "format": "epoch_second"},
                "date": {"type": "date", "format": "strict_date_optional_time"}
            }}
            self.es.indices.put_mapping(doc_type=self.beamline,
                                        index=esindex,
                                        body=mbody)
            # TODO: use regular insert rather than bulk
            eshelpers.bulk(self.es, [actions])
