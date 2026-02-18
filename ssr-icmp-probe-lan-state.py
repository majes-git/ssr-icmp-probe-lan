#!/usr/bin/env python3

from lib import parse_args, get_session, evaluate_kni


def main():
    args = parse_args()
    session = get_session()

    status, reason = evaluate_kni(session, args.kni_interface)

    if status:
        print('{"Status": ["icmp reachability-probe in progress and successful"]}')
    else:
        print(f'{{"Error": ["-> {reason}"]}}')


if __name__ == "__main__":
    main()
